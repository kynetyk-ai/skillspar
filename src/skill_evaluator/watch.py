"""Watch mode — re-run eval suites on file changes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import watchfiles
from rich.console import Console

from skill_evaluator.config.loader import (
    ConfigLoadError,
    load_eval_suite,
    resolve_config,
    resolve_skill_path,
)
from skill_evaluator.config.schema import EvalSuite
from skill_evaluator.engine.prefix import PrefixLoadError
from skill_evaluator.executor import execute_suite
from skill_evaluator.providers import missing_api_key_error
from skill_evaluator.reporting.console import ConsoleReporter, SuiteResult
from skill_evaluator.reporting.cost import build_cache_summary, build_cost_summary
from skill_evaluator.reporting.diff import diff_snapshots
from skill_evaluator.reporting.diff_display import display_diff
from skill_evaluator.reporting.json_report import JsonReporter
from skill_evaluator.skill.parser import SkillParseError

logger = logging.getLogger(__name__)


def discover_watched_files(eval_file: Path, suite: EvalSuite) -> set[Path]:
    """Collect all file paths referenced by an eval suite.

    Returns absolute paths for: the eval file itself, the skill file,
    suite-level context files, per-test context files, and the
    conversation prefix file (if external).
    """
    eval_path = eval_file.resolve()
    paths: set[Path] = {eval_path}

    # Skill file
    skill_path = resolve_skill_path(eval_path, suite.skill)
    paths.add(skill_path)

    # Suite-level context files
    if suite.context:
        for ctx in suite.context:
            paths.add((eval_path.parent / ctx.file).resolve())

    # Per-test context files
    for test in suite.tests:
        if test.context:
            for ctx in test.context:
                paths.add((eval_path.parent / ctx.file).resolve())

    # Conversation prefix external file
    if suite.conversation_prefix and suite.conversation_prefix.file:
        paths.add((eval_path.parent / suite.conversation_prefix.file).resolve())

    return paths


@dataclass
class WatchIterationResult:
    """Result of a single watch iteration."""

    suite: EvalSuite | None = None
    suite_result: SuiteResult | None = None
    report: dict[str, Any] | None = None
    cost_summary: dict[str, Any] | None = None
    cache_summary: dict[str, Any] | None = None
    error: str | None = None


def run_once(
    eval_file: Path,
    *,
    cli_runs: int | None = None,
    cli_concurrency: int | None = None,
    cli_model: str | None = None,
    cli_provider: str | None = None,
    cli_base_url: str | None = None,
    cli_filter_pattern: str | None = None,
    cli_verbose: bool = False,
) -> WatchIterationResult:
    """Execute a single eval suite run, catching expected errors.

    Returns a WatchIterationResult. On error, the `error` field is set
    and other fields are None. This ensures the watch loop survives
    syntax errors and other recoverable failures.
    """
    try:
        suite = load_eval_suite(eval_file)
    except ConfigLoadError as e:
        return WatchIterationResult(error=str(e))

    config = resolve_config(
        suite.defaults,
        cli_runs=cli_runs,
        cli_concurrency=cli_concurrency,
        cli_model=cli_model,
        cli_provider=cli_provider,
        cli_base_url=cli_base_url,
        cli_filter_pattern=cli_filter_pattern,
        cli_verbose=cli_verbose,
    )

    key_error = missing_api_key_error(config.provider, config.api_key_env)
    if key_error:
        return WatchIterationResult(error=key_error)

    # Filter tests by name substring
    if cli_filter_pattern is not None:
        pattern_lower = cli_filter_pattern.lower()
        suite.tests = [t for t in suite.tests if pattern_lower in t.name.lower()]
        if not suite.tests:
            return WatchIterationResult(error=f"No tests match filter '{cli_filter_pattern}'")

    try:
        suite_result = execute_suite(eval_file, suite, config)
    except (SkillParseError, PrefixLoadError) as e:
        return WatchIterationResult(error=str(e))
    except Exception as e:
        return WatchIterationResult(error=f"Unexpected error: {e}")

    cost_summary = build_cost_summary(suite_result, config.model)
    cache_summary = (
        build_cache_summary(suite_result, config.model) if config.provider == "anthropic" else None
    )

    json_reporter = JsonReporter()
    report = json_reporter.build_report(suite, suite_result, model=config.model)
    if cost_summary:
        report["summary"]["cost"] = cost_summary
    if cache_summary:
        report["summary"]["cache_summary"] = cache_summary

    return WatchIterationResult(
        suite=suite,
        suite_result=suite_result,
        report=report,
        cost_summary=cost_summary,
        cache_summary=cache_summary,
    )


def display_iteration(
    console: Console,
    iteration: int,
    result: WatchIterationResult,
    previous_report: dict[str, Any] | None,
    *,
    verbose: bool = False,
) -> None:
    """Render a single watch iteration to the terminal."""
    console.clear()

    timestamp = datetime.now(UTC).strftime("%H:%M:%S")
    console.print(f"[bold]Iteration {iteration}[/bold]  {timestamp}")
    console.print()

    if result.error:
        console.print(f"[red]{result.error}[/red]")
        console.print()
        console.print("[dim]Watching for changes... (Ctrl+C to stop)[/dim]")
        return

    assert result.suite_result is not None
    reporter = ConsoleReporter(console=console, verbose=verbose)
    reporter.report(
        result.suite_result,
        cost_summary=result.cost_summary,
        cache_summary=result.cache_summary,
    )

    if previous_report is not None and result.report is not None:
        diff = diff_snapshots(previous_report, result.report)
        has_changes = (
            diff.summary.regressions > 0
            or diff.summary.improvements > 0
            or diff.summary.steer_erosions > 0
            or diff.added_tests
            or diff.removed_tests
        )
        if has_changes:
            display_diff(diff, console=console)

    console.print()
    console.print("[dim]Watching for changes... (Ctrl+C to stop)[/dim]")


def watch_loop(
    eval_file: Path,
    *,
    cli_runs: int | None = None,
    cli_concurrency: int | None = None,
    cli_model: str | None = None,
    cli_provider: str | None = None,
    cli_base_url: str | None = None,
    cli_filter_pattern: str | None = None,
    cli_verbose: bool = False,
    debounce_ms: int = 300,
) -> int:
    """Top-level watch orchestrator. Returns exit code (0 = clean Ctrl+C)."""
    console = Console()
    eval_path = eval_file.resolve()

    def _run() -> WatchIterationResult:
        return run_once(
            eval_path,
            cli_runs=cli_runs,
            cli_concurrency=cli_concurrency,
            cli_model=cli_model,
            cli_provider=cli_provider,
            cli_base_url=cli_base_url,
            cli_filter_pattern=cli_filter_pattern,
            cli_verbose=cli_verbose,
        )

    iteration = 1
    previous_report: dict[str, Any] | None = None

    try:
        # Initial run
        result = _run()
        display_iteration(console, iteration, result, previous_report, verbose=cli_verbose)

        if result.report is not None:
            previous_report = result.report

        # Discover files to watch
        if result.suite is not None:
            watched = discover_watched_files(eval_path, result.suite)
        else:
            watched = {eval_path}

        while True:
            for _changes in watchfiles.watch(*watched, debounce=debounce_ms):
                iteration += 1
                result = _run()
                display_iteration(console, iteration, result, previous_report, verbose=cli_verbose)

                if result.report is not None:
                    previous_report = result.report

                # Re-discover watched files after successful runs
                if result.suite is not None:
                    new_watched = discover_watched_files(eval_path, result.suite)
                    if new_watched != watched:
                        watched = new_watched
                        break  # Restart watcher with new file set

    except KeyboardInterrupt:
        console.print()
        console.print("[dim]Watch stopped.[/dim]")
        return 0
