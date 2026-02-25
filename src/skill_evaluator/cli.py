"""CLI entry point for skillspar."""

import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from skill_evaluator.config.loader import ConfigLoadError, load_eval_suite, resolve_config
from skill_evaluator.reporting.console import ConsoleReporter
from skill_evaluator.runner import SuiteRunner

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
        sys.exit(1)

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

    # Sync resolved values back to suite.defaults for backward compat
    suite.defaults.runs = config.runs
    suite.defaults.concurrency = config.concurrency
    suite.defaults.model = config.model

    # Filter tests by name substring
    if filter_pattern is not None:
        pattern_lower = filter_pattern.lower()
        suite.tests = [t for t in suite.tests if pattern_lower in t.name.lower()]
        if not suite.tests:
            click.echo(f"Error: no tests match filter '{filter_pattern}'", err=True)
            sys.exit(1)

    runner = SuiteRunner(eval_file, suite, config=config)
    suite_result = runner.run()

    reporter = ConsoleReporter(verbose=verbose)
    reporter.report(suite_result)

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
            report = json_reporter.build_report(suite, suite_result)
            json_reporter.write(report, resolved)
            click.echo(f"JSON report written to {resolved}")

    if not suite_result.all_passed:
        sys.exit(1)
