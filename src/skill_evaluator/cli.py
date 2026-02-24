"""CLI entry point for skill-eval."""

import sys
from pathlib import Path

import click

from skill_evaluator.config.loader import ConfigLoadError, load_eval_suite
from skill_evaluator.reporting.console import ConsoleReporter
from skill_evaluator.runner import SuiteRunner


@click.group()
@click.version_option(package_name="skill-evaluator")
def main():
    """Declarative testing harness for Claude Code Agent Skills."""


@main.command()
@click.argument("eval_file", type=click.Path(exists=True))
@click.option("--runs", type=int, default=None, help="Override suite default for runs per test.")
@click.option(
    "--concurrency", type=int, default=None, help="Override suite default for max parallel API calls."
)
@click.option("--output", type=click.Path(), default=None, help="Write JSON report to file.")
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

    if output is not None:
        from skill_evaluator.reporting.json_report import JsonReporter

        json_reporter = JsonReporter()
        report = json_reporter.build_report(suite, suite_result)
        json_reporter.write(report, Path(output))
        click.echo(f"JSON report written to {output}")

    if not suite_result.all_passed:
        sys.exit(1)
