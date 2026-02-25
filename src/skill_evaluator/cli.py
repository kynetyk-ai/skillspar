"""CLI entry point for skillspar."""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

from skill_evaluator.config.loader import ConfigLoadError, load_eval_suite
from skill_evaluator.reporting.console import ConsoleReporter
from skill_evaluator.runner import SuiteRunner


def _slugify(name: str) -> str:
    """Convert a suite name to a filename-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


def _resolve_output_path(output: str | None, output_format: str, suite_name: str) -> Path | None:
    """Resolve the output file path from --output flag and format."""
    if output is None:
        output = os.environ.get("SKILLSPAR_OUTPUT")
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
def run(eval_file, runs, concurrency, output, output_format, filter_pattern, model, verbose):
    """Run an eval suite from a .eval.yaml file."""
    try:
        suite = load_eval_suite(eval_file)
    except ConfigLoadError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if runs is not None:
        suite.defaults.runs = runs
    if concurrency is not None:
        suite.defaults.concurrency = concurrency
    if model is not None:
        suite.defaults.model = model

    # Filter tests by name substring
    if filter_pattern is not None:
        pattern_lower = filter_pattern.lower()
        suite.tests = [t for t in suite.tests if pattern_lower in t.name.lower()]
        if not suite.tests:
            click.echo(f"Error: no tests match filter '{filter_pattern}'", err=True)
            sys.exit(1)

    runner = SuiteRunner(eval_file, suite)
    suite_result = runner.run()

    reporter = ConsoleReporter(verbose=verbose)
    reporter.report(suite_result)

    # Determine format: explicit flag > extension inference > json default
    if output_format is None:
        if output and Path(output).suffix == ".xml":
            output_format = "junit"
        else:
            output_format = "json"

    resolved = _resolve_output_path(output, output_format, suite.suite)

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
