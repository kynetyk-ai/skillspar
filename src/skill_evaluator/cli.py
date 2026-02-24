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
@click.option("--output", type=click.Path(), default=None, help="Directory for JSON report output.")
def run(eval_file, runs, concurrency, output):
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

    runner = SuiteRunner(eval_file, suite)
    suite_result = runner.run()

    reporter = ConsoleReporter()
    reporter.report(suite_result)

    output_dir = output or os.environ.get("SKILLSPAR_OUTPUT")
    if output_dir is not None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        slug = _slugify(suite.suite)
        filename = f"{slug}_{timestamp}.json"
        resolved = Path(output_dir).resolve() / filename
    else:
        resolved = None

    if resolved is not None:
        from skill_evaluator.reporting.json_report import JsonReporter

        json_reporter = JsonReporter()
        report = json_reporter.build_report(suite, suite_result)
        json_reporter.write(report, resolved)
        click.echo(f"JSON report written to {resolved}")

    if not suite_result.all_passed:
        sys.exit(1)
