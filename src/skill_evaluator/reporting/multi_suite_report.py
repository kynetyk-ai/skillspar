"""Multi-suite reporting — aggregated dashboard, combined JSON, combined JUnit."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from rich.console import Console
from rich.table import Table

from skill_evaluator.multi_suite import MultiSuiteResult, SuiteOutcome
from skill_evaluator.reporting.json_report import JsonReporter
from skill_evaluator.reporting.junit import JunitReporter


def display_multi_suite_summary(
    result: MultiSuiteResult,
    console: Console | None = None,
    *,
    verbose: bool = False,
) -> None:
    """Render an aggregated dashboard table to the terminal."""
    console = console or Console()

    console.print()
    console.print("[bold]Multi-Suite Summary[/bold]")
    console.print()

    table = Table(show_header=True, header_style="bold", show_lines=False, pad_edge=False)
    table.add_column("Suite", min_width=20)
    table.add_column("Status", justify="center", min_width=6)
    table.add_column("Tests", justify="center", min_width=8)
    table.add_column("Cost", justify="right", min_width=8)

    for outcome in result.outcomes:
        name = outcome.suite_name
        status, tests_str, cost_str = _outcome_row(outcome)
        table.add_row(name, status, tests_str, cost_str)

    console.print(table)
    console.print()

    # Summary line
    parts = []
    if result.error_suites > 0:
        parts.append(f"{result.error_suites} errored")
    if result.failed_suites > 0:
        parts.append(f"{result.failed_suites} failed")
    if result.passed_suites > 0:
        parts.append(f"{result.passed_suites} passed")

    summary_text = f"{result.total_suites} suites: {', '.join(parts)}"

    if result.all_passed:
        console.print(f"[green bold]{summary_text}[/green bold]")
    else:
        console.print(f"[red bold]{summary_text}[/red bold]")

    # Total cost
    total_cost = _total_cost(result)
    if total_cost is not None:
        console.print(f"[dim]Total cost: ${total_cost:.2f}[/dim]")


def _outcome_row(outcome: SuiteOutcome) -> tuple[str, str, str]:
    """Build status, tests, and cost strings for a single outcome."""
    if outcome.error is not None:
        return "[yellow]ERROR[/yellow]", "—", "—"

    sr = outcome.suite_result
    total = len(sr.test_results)
    passed = sr.passed_count

    if sr.all_passed:
        status = "[green]PASS[/green]"
    else:
        status = "[red]FAIL[/red]"

    tests_str = f"{passed}/{total}"

    cost_str = "—"
    if outcome.cost_summary:
        total_cost = outcome.cost_summary.get("total_cost_usd", 0)
        cost_str = f"${total_cost:.2f}"

    return status, tests_str, cost_str


def _total_cost(result: MultiSuiteResult) -> float | None:
    """Sum costs across all outcomes. Returns None if no cost data."""
    total = 0.0
    has_cost = False
    for outcome in result.outcomes:
        if outcome.cost_summary:
            total += outcome.cost_summary.get("total_cost_usd", 0)
            has_cost = True
    return total if has_cost else None


def build_multi_suite_json_report(result: MultiSuiteResult) -> dict[str, Any]:
    """Build a combined JSON report across all suites."""
    json_reporter = JsonReporter()
    suites = []

    for outcome in result.outcomes:
        if outcome.error is not None:
            suites.append({
                "eval_file": str(outcome.eval_file),
                "suite": outcome.suite_name,
                "error": outcome.error,
            })
            continue

        report = json_reporter.build_report(
            outcome.suite, outcome.suite_result, model=outcome.config.model
        )
        if outcome.cost_summary:
            report["summary"]["cost"] = outcome.cost_summary
        if outcome.cache_summary:
            report["summary"]["cache_summary"] = outcome.cache_summary
        report["eval_file"] = str(outcome.eval_file)
        suites.append(report)

    total_cost = _total_cost(result)

    summary: dict[str, Any] = {
        "total_suites": result.total_suites,
        "passed_suites": result.passed_suites,
        "failed_suites": result.failed_suites,
        "error_suites": result.error_suites,
        "all_passed": result.all_passed,
    }
    if total_cost is not None:
        summary["total_cost_usd"] = round(total_cost, 6)

    return {
        "schema_version": "1",
        "type": "multi_suite",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "suites": suites,
        "summary": summary,
    }


def build_multi_suite_junit_report(result: MultiSuiteResult) -> ET.Element:
    """Build a combined JUnit XML report with a single <testsuites> root."""
    root = ET.Element("testsuites")
    junit_reporter = JunitReporter()

    for outcome in result.outcomes:
        if outcome.error is not None:
            # Represent errored suites as a single failed testsuite
            ts = ET.SubElement(
                root, "testsuite",
                name=outcome.suite_name,
                tests="0",
                failures="0",
                errors="1",
            )
            tc = ET.SubElement(ts, "testcase", name=outcome.suite_name)
            err = ET.SubElement(tc, "error", message=outcome.error)
            err.text = outcome.error
            continue

        # Build per-suite JUnit and merge its children into the root
        suite_root = junit_reporter.build_report(outcome.suite, outcome.suite_result)
        for child in suite_root:
            root.append(child)

    return root
