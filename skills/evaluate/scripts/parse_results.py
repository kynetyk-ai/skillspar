#!/usr/bin/env python3
"""Parse Skillspar JSON report files into LLM-friendly summaries.

Usage:
    python parse_results.py <path-to-results.json>
    cat results.json | python parse_results.py

Standalone script — requires only stdlib json (no dependencies).
Auto-detects single-suite vs multi-suite reports.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

MAX_OUTPUT_EXCERPT = 500


def _format_assertion(assertion: dict) -> str:
    """Format a single assertion result."""
    status = assertion.get("status", "unknown")
    atype = assertion.get("type", "unknown")
    message = assertion.get("message", "")
    marker = "PASSED" if status == "passed" else "FAILED"
    return f"      [{atype}] {marker}: {message}"


def _get_model_output_excerpt(run: dict) -> str | None:
    """Extract a truncated model output excerpt from a run's trace."""
    trace = run.get("trace")
    if not trace:
        return None
    turns = trace.get("turns", [])
    if not turns:
        return None
    # Collect all text output across turns
    parts = []
    for turn in turns:
        text = turn.get("text_output", "")
        if text:
            parts.append(text)
    if not parts:
        return None
    full = "\n".join(parts)
    if len(full) > MAX_OUTPUT_EXCERPT:
        return full[:MAX_OUTPUT_EXCERPT] + "..."
    return full


def _format_baseline_tag(test: dict) -> str:
    """Format baseline comparison string if baseline data exists."""
    bs = test.get("baseline_summary")
    if not bs:
        return ""
    return f", baseline: {bs['pass_count']}/{bs['total_runs']}"


def _format_pass_rate(summary: dict, config: dict) -> str:
    """Format pass rate with threshold if applicable."""
    runs = summary["total_runs"]
    passed = summary["pass_count"]
    threshold = config.get("pass_threshold", 1.0)
    if runs == 1:
        return f"{passed}/{runs} runs"
    parts = f"{passed}/{runs} runs"
    if threshold < 1.0:
        parts += f", threshold: {threshold:.0%}"
    return parts


# ---------------------------------------------------------------------------
# Single-suite formatting
# ---------------------------------------------------------------------------


def _format_single_suite(report: dict) -> str:
    """Format a single-suite report into a readable summary."""
    lines: list[str] = []

    suite_name = report.get("suite", "unnamed")
    tests = report.get("tests", [])
    summary = report.get("summary", {})

    total = summary.get("total_tests", len(tests))
    passed = summary.get("passed_tests", 0)
    failed = summary.get("failed_tests", 0)

    # Header
    lines.append(f'RESULTS: suite "{suite_name}" ({total} tests, {passed} passed, {failed} failed)')

    # Metadata line
    meta_parts = []
    defaults = report.get("defaults", {})
    model = defaults.get("model", "")
    if model:
        meta_parts.append(f"Model: {model}")

    cost = summary.get("cost", {})
    total_cost = cost.get("total_cost_usd")
    if total_cost is not None:
        meta_parts.append(f"Cost: ${total_cost:.2f}")

    duration = summary.get("total_duration_seconds")
    if duration is not None:
        meta_parts.append(f"Duration: {duration:.1f}s")

    if meta_parts:
        lines.append(" | ".join(meta_parts))

    # Separate passed and failed tests
    passed_tests = [t for t in tests if t.get("summary", {}).get("passed")]
    failed_tests = [t for t in tests if not t.get("summary", {}).get("passed")]

    # Passed tests (compact)
    if passed_tests:
        lines.append("")
        lines.append("PASSED TESTS:")
        for test in passed_tests:
            name = test.get("name", "unnamed")
            s = test.get("summary", {})
            c = test.get("config", {})
            rate = _format_pass_rate(s, c)
            bl = _format_baseline_tag(test)
            lines.append(f"  \u2713 {name} ({rate}{bl})")

    # Failed tests (detailed)
    if failed_tests:
        lines.append("")
        lines.append("FAILED TESTS:")
        for test in failed_tests:
            name = test.get("name", "unnamed")
            s = test.get("summary", {})
            c = test.get("config", {})
            rate = _format_pass_rate(s, c)
            bl = _format_baseline_tag(test)
            lines.append(f"  \u2717 {name} ({rate}{bl})")

            # Show each run's details
            for run in test.get("runs", []):
                idx = run.get("run_index", 0)
                run_passed = run.get("passed", False)
                if run_passed:
                    lines.append(f"    Run {idx}: PASS")
                else:
                    lines.append(f"    Run {idx}: FAIL")
                    for assertion in run.get("assertions", []):
                        lines.append(_format_assertion(assertion))
                    # Show model output excerpt for failed runs
                    excerpt = _get_model_output_excerpt(run)
                    if excerpt:
                        lines.append(
                            f'      Model output (first {MAX_OUTPUT_EXCERPT} chars): "{excerpt}"'
                        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Multi-suite formatting
# ---------------------------------------------------------------------------


def _format_multi_suite(report: dict) -> str:
    """Format a multi-suite report into a readable summary."""
    lines: list[str] = []

    suites = report.get("suites", [])
    summary = report.get("summary", {})

    total_suites = summary.get("total_suites", len(suites))
    passed_suites = summary.get("passed_suites", 0)
    failed_suites = summary.get("failed_suites", 0)
    error_suites = summary.get("error_suites", 0)

    lines.append(
        f"MULTI-SUITE RESULTS: {total_suites} suites, "
        f"{passed_suites} passed, {failed_suites} failed, {error_suites} errors"
    )

    total_cost = summary.get("total_cost_usd")
    if total_cost is not None:
        lines.append(f"Total cost: ${total_cost:.2f}")

    # Summary table
    lines.append("")
    lines.append(f"{'Suite':<40} {'Status':<8} {'Tests':<10} {'Cost':<10}")
    lines.append("-" * 68)

    for suite in suites:
        name = suite.get("suite", Path(suite.get("eval_file", "unknown")).stem)

        if "error" in suite:
            lines.append(f"{name:<40} {'ERROR':<8} {'-':<10} {'-':<10}")
            continue

        s = suite.get("summary", {})
        passed = s.get("passed_tests", 0)
        total = s.get("total_tests", 0)
        status = "PASS" if s.get("all_passed") else "FAIL"
        cost = s.get("cost", {}).get("total_cost_usd")
        cost_str = f"${cost:.2f}" if cost is not None else "-"
        lines.append(f"{name:<40} {status:<8} {passed}/{total:<7} {cost_str:<10}")

    # Detail sections for failures and errors only
    for suite in suites:
        if "error" in suite:
            name = suite.get("suite", Path(suite.get("eval_file", "unknown")).stem)
            lines.append("")
            lines.append(f"--- {name} (ERROR) ---")
            lines.append(f"  {suite['error']}")
            continue

        s = suite.get("summary", {})
        if s.get("all_passed"):
            continue

        # Show failed suite details
        lines.append("")
        lines.append(_format_single_suite(suite))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report type detection
# ---------------------------------------------------------------------------


def parse_report(data: dict) -> str:
    """Auto-detect report type and format it."""
    if data.get("type") == "multi_suite":
        return _format_multi_suite(data)
    if "tests" in data and "suite" in data:
        return _format_single_suite(data)
    return f"ERROR: Unrecognized report format. Keys found: {list(data.keys())}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help")):
        print("Usage: python parse_results.py [<path-to-results.json>]", file=sys.stderr)
        print("       cat results.json | python parse_results.py", file=sys.stderr)
        print()
        print("Parse a Skillspar JSON report into an LLM-friendly summary.", file=sys.stderr)
        print("Reads from file argument or stdin.", file=sys.stderr)
        sys.exit(0)

    if len(sys.argv) == 2:
        path = Path(sys.argv[1])
        if not path.exists():
            print(f"ERROR: File not found: {path}", file=sys.stderr)
            sys.exit(2)
        text = path.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(data, dict):
        print("ERROR: Expected a JSON object at the top level", file=sys.stderr)
        sys.exit(2)

    print(parse_report(data))


if __name__ == "__main__":
    main()
