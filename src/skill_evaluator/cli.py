"""CLI entry point for skillspar."""

import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from skill_evaluator.config.loader import ConfigLoadError, load_eval_suite, resolve_config
from skill_evaluator.engine.prefix import PrefixLoadError
from skill_evaluator.executor import execute_suite
from skill_evaluator.reporting.console import ConsoleReporter
from skill_evaluator.skill.parser import SkillParseError

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Convert a suite name to a filename-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


def _resolve_output_path(output: str | None, output_format: str, suite_name: str) -> Path | None:
    """Resolve the output file path from --output flag and format."""
    if output is None:
        return None

    path = Path(output).resolve()

    # If --output ends with a known extension, treat it as a file path directly
    if path.suffix in (".json", ".xml"):
        return path

    # Otherwise treat as a directory and auto-generate a filename
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    slug = _slugify(suite_name)
    ext = "xml" if output_format == "junit" else "json"
    return path / f"{slug}_{timestamp}.{ext}"


def _setup_logging(log_level: str | None) -> None:
    """Configure the root skill_evaluator logger."""
    if log_level is None:
        log_level = os.environ.get("SKILLSPAR_LOG_LEVEL", "WARNING")
    level = getattr(logging, log_level.upper(), logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("skill_evaluator").setLevel(level)
    # Silence noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)


@click.group()
@click.version_option(package_name="skillspar")
def main():
    """Declarative testing harness for Claude Code Agent Skills."""


@main.command()
@click.argument("eval_file", type=click.Path(exists=True))
@click.option("--runs", type=int, default=None, help="Override suite default for runs per test.")
@click.option(
    "--concurrency", type=int, default=None, help="Override suite default for max parallel API calls."
)
@click.option("--output", type=click.Path(), default=None, help="Output path for report file.")
@click.option(
    "--format", "output_format", type=click.Choice(["json", "junit"]), default=None,
    help="Report format (default: inferred from --output extension, or json).",
)
@click.option(
    "--filter", "filter_pattern", type=str, default=None,
    help="Only run tests whose name contains this substring.",
)
@click.option(
    "--model", type=str, default=None,
    help="Override the suite default model.",
)
@click.option(
    "--verbose", is_flag=True, default=False,
    help="Show per-assertion details in console output.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default=None,
    help="Set logging verbosity (default: WARNING).",
)
def run(eval_file, runs, concurrency, output, output_format, filter_pattern, model, verbose, log_level):
    """Run an eval suite from a .eval.yaml file."""
    from dotenv import load_dotenv

    load_dotenv()

    _setup_logging(log_level)

    try:
        suite = load_eval_suite(eval_file)
    except ConfigLoadError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)

    # Resolve format before config so we can pass it through
    if output_format is None:
        if output and Path(output).suffix == ".xml":
            output_format = "junit"
        else:
            output_format = "json"

    config = resolve_config(
        suite.defaults,
        cli_runs=runs,
        cli_concurrency=concurrency,
        cli_model=model,
        cli_output=output,
        cli_output_format=output_format,
        cli_verbose=verbose,
        cli_filter_pattern=filter_pattern,
    )

    # Filter tests by name substring
    if filter_pattern is not None:
        pattern_lower = filter_pattern.lower()
        suite.tests = [t for t in suite.tests if pattern_lower in t.name.lower()]
        if not suite.tests:
            click.echo(f"Error: no tests match filter '{filter_pattern}'", err=True)
            sys.exit(2)

    try:
        suite_result = execute_suite(Path(eval_file), suite, config)
    except (SkillParseError, PrefixLoadError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)

    # Compute cost and cache summaries
    from skill_evaluator.reporting.cost import build_cost_summary, estimate_cache_savings

    cost_summary = build_cost_summary(suite_result, config.model)

    # Build cache summary
    cache_summary = None
    total_cache_creation = 0
    total_cache_read = 0
    has_cache = False
    for group in suite_result.test_results:
        all_runs = list(group.runs) + (group.baseline_runs or [])
        for r in all_runs:
            if r.trace:
                u = r.trace.total_usage
                if u.cache_creation_input_tokens is not None:
                    total_cache_creation += u.cache_creation_input_tokens
                    has_cache = True
                if u.cache_read_input_tokens is not None:
                    total_cache_read += u.cache_read_input_tokens
                    has_cache = True
    if has_cache:
        savings = estimate_cache_savings(total_cache_read, config.model)
        cache_summary = {
            "cache_creation_input_tokens": total_cache_creation,
            "cache_read_input_tokens": total_cache_read,
            "estimated_savings_usd": round(savings, 6) if savings is not None else None,
        }

    reporter = ConsoleReporter(verbose=verbose)
    reporter.report(suite_result, cost_summary=cost_summary, cache_summary=cache_summary)

    resolved = _resolve_output_path(config.output, output_format, suite.suite)

    if resolved is not None:
        if output_format == "junit":
            from skill_evaluator.reporting.junit import JunitReporter

            junit_reporter = JunitReporter()
            report = junit_reporter.build_report(suite, suite_result)
            junit_reporter.write(report, resolved)
            click.echo(f"JUnit report written to {resolved}")
        else:
            from skill_evaluator.reporting.json_report import JsonReporter

            json_reporter = JsonReporter()
            report = json_reporter.build_report(suite, suite_result, model=config.model)
            # Inject cost and cache data into report summary
            if cost_summary:
                report["summary"]["cost"] = cost_summary
            if cache_summary:
                report["summary"]["cache_summary"] = cache_summary
            json_reporter.write(report, resolved)
            click.echo(f"JSON report written to {resolved}")

    if not suite_result.all_passed:
        sys.exit(1)


def _run_suite_and_build_report(eval_file, model_override=None):
    """Load, execute, and build a JSON report for a suite. Returns (suite, report, suite_result)."""
    from dotenv import load_dotenv

    from skill_evaluator.reporting.cost import build_cost_summary, estimate_cache_savings
    from skill_evaluator.reporting.json_report import JsonReporter

    load_dotenv()

    try:
        suite = load_eval_suite(eval_file)
    except ConfigLoadError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)

    config = resolve_config(suite.defaults, cli_model=model_override)

    try:
        suite_result = execute_suite(Path(eval_file), suite, config)
    except (SkillParseError, PrefixLoadError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)

    cost_summary = build_cost_summary(suite_result, config.model)

    # Build cache summary
    cache_summary = None
    total_cache_creation = 0
    total_cache_read = 0
    has_cache = False
    for group in suite_result.test_results:
        all_runs = list(group.runs) + (group.baseline_runs or [])
        for r in all_runs:
            if r.trace:
                u = r.trace.total_usage
                if u.cache_creation_input_tokens is not None:
                    total_cache_creation += u.cache_creation_input_tokens
                    has_cache = True
                if u.cache_read_input_tokens is not None:
                    total_cache_read += u.cache_read_input_tokens
                    has_cache = True
    if has_cache:
        savings = estimate_cache_savings(total_cache_read, config.model)
        cache_summary = {
            "cache_creation_input_tokens": total_cache_creation,
            "cache_read_input_tokens": total_cache_read,
            "estimated_savings_usd": round(savings, 6) if savings is not None else None,
        }

    reporter = ConsoleReporter(verbose=False)
    reporter.report(suite_result, cost_summary=cost_summary, cache_summary=cache_summary)

    json_reporter = JsonReporter()
    report = json_reporter.build_report(suite, suite_result, model=config.model)
    if cost_summary:
        report["summary"]["cost"] = cost_summary
    if cache_summary:
        report["summary"]["cache_summary"] = cache_summary

    return suite, report, suite_result


# --- Snapshot subcommand group ---


@main.group()
def snapshot():
    """Manage saved snapshots and diffs."""


@snapshot.command("save")
@click.argument("eval_file", type=click.Path(exists=True))
@click.option(
    "--snapshot-dir", type=click.Path(), default=None,
    help="Override snapshot directory (default: .skillspar/snapshots/).",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default=None,
    help="Set logging verbosity (default: WARNING).",
)
def snapshot_save(eval_file, snapshot_dir, log_level):
    """Run a suite and save the result as a snapshot."""
    from skill_evaluator.reporting.snapshot import save_snapshot

    _setup_logging(log_level)
    snapshot_path = Path(snapshot_dir) if snapshot_dir else None

    _suite, report, _result = _run_suite_and_build_report(eval_file)
    path = save_snapshot(report, snapshot_dir=snapshot_path)
    click.echo(f"Snapshot saved to {path}")


@snapshot.command("list")
@click.option("--suite", "suite_name", type=str, default=None, help="Filter by suite name.")
@click.option(
    "--snapshot-dir", type=click.Path(), default=None,
    help="Override snapshot directory (default: .skillspar/snapshots/).",
)
def snapshot_list(suite_name, snapshot_dir):
    """List saved snapshots."""
    from skill_evaluator.reporting.snapshot import list_snapshots

    snapshot_path = Path(snapshot_dir) if snapshot_dir else None
    snaps = list_snapshots(suite_name=suite_name, snapshot_dir=snapshot_path)

    if not snaps:
        click.echo("No snapshots found.")
        return

    for s in snaps:
        run_id_str = f"  run_id={s.run_id}" if s.run_id else ""
        click.echo(f"  {s.timestamp}  {s.suite_name}{run_id_str}  {s.path}")


@snapshot.command("diff")
@click.argument("before", type=click.Path(exists=True), required=False)
@click.argument("after", type=click.Path(exists=True), required=False)
@click.option(
    "--latest", "eval_file", type=click.Path(exists=True), default=None,
    help="Run a suite and diff against the most recent saved snapshot.",
)
@click.option(
    "--snapshot-dir", type=click.Path(), default=None,
    help="Override snapshot directory (default: .skillspar/snapshots/).",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default=None,
    help="Set logging verbosity (default: WARNING).",
)
def snapshot_diff(before, after, eval_file, snapshot_dir, log_level):
    """Diff two snapshots, or diff latest snapshot against a new run.

    Usage:

      skillspar snapshot diff <before.json> <after.json>

      skillspar snapshot diff --latest <eval_file>
    """
    from skill_evaluator.reporting.diff import diff_snapshots
    from skill_evaluator.reporting.diff_display import display_diff
    from skill_evaluator.reporting.snapshot import (
        SnapshotLoadError,
        find_latest_snapshot,
        load_snapshot,
        save_snapshot,
    )

    _setup_logging(log_level)
    snapshot_path = Path(snapshot_dir) if snapshot_dir else None

    if eval_file:
        # --latest mode: run suite, diff against most recent snapshot
        suite, report, _result = _run_suite_and_build_report(eval_file)
        previous = find_latest_snapshot(suite.suite, snapshot_dir=snapshot_path)

        # Save the new run as a snapshot
        saved = save_snapshot(report, snapshot_dir=snapshot_path)
        click.echo(f"Snapshot saved to {saved}")

        if previous is None:
            click.echo("No previous snapshot to compare — saved as first snapshot.")
            return

        try:
            before_data = load_snapshot(previous)
        except SnapshotLoadError as e:
            click.echo(f"Error loading previous snapshot: {e}", err=True)
            sys.exit(2)

        result = diff_snapshots(before_data, report)
        display_diff(result)
    elif before and after:
        # Explicit two-file diff
        try:
            before_data = load_snapshot(Path(before))
            after_data = load_snapshot(Path(after))
        except SnapshotLoadError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(2)

        result = diff_snapshots(before_data, after_data)
        display_diff(result)
    else:
        click.echo(
            "Error: provide two snapshot files, or use --latest <eval_file>.",
            err=True,
        )
        sys.exit(2)
