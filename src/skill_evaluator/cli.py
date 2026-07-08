"""CLI entry point for skillspar."""

import json
import logging
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import click

from skill_evaluator.config.loader import ConfigLoadError, load_eval_suite, resolve_config
from skill_evaluator.engine.prefix import PrefixLoadError
from skill_evaluator.executor import execute_suite
from skill_evaluator.reporting.console import ConsoleReporter
from skill_evaluator.skill.parser import SkillParseError
from skill_evaluator.tools.registry import ToolRegistryError

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
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
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
    logging.getLogger("openai").setLevel(logging.WARNING)


def _check_api_key(provider: str = "anthropic", api_key_env: str | None = None) -> None:
    """Fail fast if the provider's API key env var is not set."""
    from skill_evaluator.providers import missing_api_key_error

    message = missing_api_key_error(provider, api_key_env)
    if message:
        click.echo(message, err=True)
        sys.exit(2)


@click.group()
@click.version_option(package_name="skillspar")
def main():
    """Declarative testing harness for Claude Code Agent Skills."""


@main.command()
@click.argument("eval_files", nargs=-1, required=True)
@click.option("--runs", type=int, default=None, help="Override suite default for runs per test.")
@click.option(
    "--concurrency",
    type=int,
    default=None,
    help="Override suite default for max parallel API calls.",
)
@click.option("--output", type=click.Path(), default=None, help="Output path for report file.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "junit"]),
    default=None,
    help="Report format (default: inferred from --output extension, or json).",
)
@click.option(
    "--filter",
    "filter_pattern",
    type=str,
    default=None,
    help="Only run tests whose name contains this substring.",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="Override the suite default model.",
)
@click.option(
    "--provider",
    type=click.Choice(["anthropic", "openai"]),
    default=None,
    help="Override the suite default provider.",
)
@click.option(
    "--base-url",
    type=str,
    default=None,
    help="Override the API base URL (OpenAI-compatible endpoints).",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Show per-assertion details in console output.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default=None,
    help="Set logging verbosity (default: WARNING).",
)
def run(
    eval_files,
    runs,
    concurrency,
    output,
    output_format,
    filter_pattern,
    model,
    provider,
    base_url,
    verbose,
    log_level,
):
    """Run eval suites from .eval.yaml files.

    Accepts one or more files, directories, or glob patterns. Directories are
    searched recursively for *.eval.yaml files.
    """
    from dotenv import load_dotenv

    from skill_evaluator.discovery import DiscoveryError, resolve_eval_paths

    load_dotenv()
    _setup_logging(log_level)

    # Resolve format
    if output_format is None:
        if output and Path(output).suffix == ".xml":
            output_format = "junit"
        else:
            output_format = "json"

    try:
        resolved_paths = resolve_eval_paths(eval_files)
    except DiscoveryError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)

    if len(resolved_paths) == 1:
        _run_single_suite(
            resolved_paths[0],
            runs=runs,
            concurrency=concurrency,
            output=output,
            output_format=output_format,
            filter_pattern=filter_pattern,
            model=model,
            provider=provider,
            base_url=base_url,
            verbose=verbose,
        )
    else:
        _run_multi_suite(
            resolved_paths,
            runs=runs,
            concurrency=concurrency,
            output=output,
            output_format=output_format,
            filter_pattern=filter_pattern,
            model=model,
            provider=provider,
            base_url=base_url,
            verbose=verbose,
        )


def _load_and_execute(
    eval_file,
    *,
    cli_runs=None,
    cli_concurrency=None,
    cli_model=None,
    cli_provider=None,
    cli_base_url=None,
    cli_output=None,
    cli_output_format=None,
    cli_verbose=False,
    cli_filter_pattern=None,
):
    """Load, execute, and summarise a suite.

    Returns (suite, config, suite_result, cost_summary, cache_summary, json_report).
    """
    from skill_evaluator.reporting.cost import build_cache_summary, build_cost_summary
    from skill_evaluator.reporting.json_report import JsonReporter

    try:
        suite = load_eval_suite(eval_file)
    except ConfigLoadError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)

    config = resolve_config(
        suite.defaults,
        cli_runs=cli_runs,
        cli_concurrency=cli_concurrency,
        cli_model=cli_model,
        cli_provider=cli_provider,
        cli_base_url=cli_base_url,
        cli_output=cli_output,
        cli_output_format=cli_output_format,
        cli_verbose=cli_verbose,
        cli_filter_pattern=cli_filter_pattern,
    )

    _check_api_key(config.provider, config.api_key_env)
    if config.judge_provider and config.judge_provider != config.provider:
        _check_api_key(config.judge_provider)

    if cli_filter_pattern is not None:
        pattern_lower = cli_filter_pattern.lower()
        suite.tests = [t for t in suite.tests if pattern_lower in t.name.lower()]
        if not suite.tests:
            click.echo(f"Error: no tests match filter '{cli_filter_pattern}'", err=True)
            sys.exit(2)

    try:
        suite_result = execute_suite(Path(eval_file), suite, config)
    except (SkillParseError, PrefixLoadError, ToolRegistryError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)

    cost_summary = build_cost_summary(suite_result, config.model)
    cache_summary = (
        build_cache_summary(suite_result, config.model) if config.provider == "anthropic" else None
    )

    json_reporter = JsonReporter()
    json_report = json_reporter.build_report(suite, suite_result, model=config.model)
    if cost_summary:
        json_report["summary"]["cost"] = cost_summary
    if cache_summary:
        json_report["summary"]["cache_summary"] = cache_summary

    return suite, config, suite_result, cost_summary, cache_summary, json_report


def _run_single_suite(
    eval_file: Path,
    *,
    runs,
    concurrency,
    output,
    output_format,
    filter_pattern,
    model,
    provider,
    base_url,
    verbose,
) -> None:
    """Run a single eval suite — preserves original single-file behavior."""
    suite, config, suite_result, cost_summary, cache_summary, json_report = _load_and_execute(
        eval_file,
        cli_runs=runs,
        cli_concurrency=concurrency,
        cli_model=model,
        cli_provider=provider,
        cli_base_url=base_url,
        cli_output=output,
        cli_output_format=output_format,
        cli_verbose=verbose,
        cli_filter_pattern=filter_pattern,
    )

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
            json_reporter.write(json_report, resolved)
            click.echo(f"JSON report written to {resolved}")

    if not suite_result.all_passed:
        sys.exit(1)


def _run_multi_suite(
    eval_files: list[Path],
    *,
    runs,
    concurrency,
    output,
    output_format,
    filter_pattern,
    model,
    provider,
    base_url,
    verbose,
) -> None:
    """Run multiple eval suites with aggregated reporting."""
    from skill_evaluator.multi_suite import run_suites
    from skill_evaluator.reporting.multi_suite_report import (
        build_multi_suite_json_report,
        build_multi_suite_junit_report,
        display_multi_suite_summary,
    )

    result = run_suites(
        eval_files,
        cli_runs=runs,
        cli_concurrency=concurrency,
        cli_model=model,
        cli_provider=provider,
        cli_base_url=base_url,
        cli_output=output,
        cli_output_format=output_format,
        cli_verbose=verbose,
        cli_filter_pattern=filter_pattern,
    )

    # Print per-suite results as they were collected
    reporter = ConsoleReporter(verbose=verbose)
    for outcome in result.outcomes:
        if outcome.error is not None:
            click.echo(f"\nError in {outcome.eval_file}: {outcome.error}", err=True)
        elif outcome.suite_result is not None:
            reporter.report(
                outcome.suite_result,
                cost_summary=outcome.cost_summary,
                cache_summary=outcome.cache_summary,
            )

    # Aggregated dashboard
    display_multi_suite_summary(result, verbose=verbose)

    # Write combined report
    if output is not None:
        output_path = Path(output).resolve()
        if output_format == "junit":
            junit_root = build_multi_suite_junit_report(result)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            tree = ET.ElementTree(junit_root)
            ET.indent(tree, space="  ")
            tree.write(output_path, encoding="unicode", xml_declaration=True)
            click.echo(f"JUnit report written to {output_path}")
        else:
            report = build_multi_suite_json_report(result)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(report, f, indent=2)
            click.echo(f"JSON report written to {output_path}")

    # Exit codes: 2 = config errors (takes priority), 1 = test failures, 0 = all pass
    if result.has_config_errors:
        sys.exit(2)
    if not result.all_passed:
        sys.exit(1)


@main.command()
@click.argument("eval_file", type=click.Path(exists=True))
@click.option("--runs", type=int, default=None, help="Override suite default for runs per test.")
@click.option(
    "--concurrency",
    type=int,
    default=None,
    help="Override suite default for max parallel API calls.",
)
@click.option(
    "--filter",
    "filter_pattern",
    type=str,
    default=None,
    help="Only run tests whose name contains this substring.",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="Override the suite default model.",
)
@click.option(
    "--provider",
    type=click.Choice(["anthropic", "openai"]),
    default=None,
    help="Override the suite default provider.",
)
@click.option(
    "--base-url",
    type=str,
    default=None,
    help="Override the API base URL (OpenAI-compatible endpoints).",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Show per-assertion details in console output.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default=None,
    help="Set logging verbosity (default: WARNING).",
)
@click.option(
    "--debounce",
    type=int,
    default=300,
    help="Debounce interval in milliseconds (default: 300).",
)
def watch(
    eval_file,
    runs,
    concurrency,
    filter_pattern,
    model,
    provider,
    base_url,
    verbose,
    log_level,
    debounce,
):
    """Watch files and re-run an eval suite on changes."""
    from dotenv import load_dotenv

    from skill_evaluator.watch import watch_loop

    load_dotenv()
    _setup_logging(log_level)

    exit_code = watch_loop(
        Path(eval_file),
        cli_runs=runs,
        cli_concurrency=concurrency,
        cli_model=model,
        cli_provider=provider,
        cli_base_url=base_url,
        cli_filter_pattern=filter_pattern,
        cli_verbose=verbose,
        debounce_ms=debounce,
    )
    sys.exit(exit_code)


def _run_suite_and_build_report(eval_file, model_override=None):
    """Load, execute, and build a JSON report for a suite. Returns (suite, report, suite_result)."""
    from dotenv import load_dotenv

    load_dotenv()

    suite, _config, suite_result, cost_summary, cache_summary, report = _load_and_execute(
        eval_file,
        cli_model=model_override,
    )

    reporter = ConsoleReporter(verbose=False)
    reporter.report(suite_result, cost_summary=cost_summary, cache_summary=cache_summary)

    return suite, report, suite_result


# --- Snapshot subcommand group ---


@main.group()
def snapshot():
    """Manage saved snapshots and diffs."""


@snapshot.command("save")
@click.argument("eval_file", type=click.Path(exists=True))
@click.option(
    "--snapshot-dir",
    type=click.Path(),
    default=None,
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
    "--snapshot-dir",
    type=click.Path(),
    default=None,
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
    "--latest",
    "eval_file",
    type=click.Path(exists=True),
    default=None,
    help="Run a suite and diff against the most recent saved snapshot.",
)
@click.option(
    "--snapshot-dir",
    type=click.Path(),
    default=None,
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
