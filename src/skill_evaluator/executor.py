"""High-level API for running eval suites programmatically."""

from __future__ import annotations

from pathlib import Path

from skill_evaluator.config.schema import EvalSuite, ResolvedConfig
from skill_evaluator.reporting.console import SuiteResult
from skill_evaluator.runner import SuiteRunner


def execute_suite(
    eval_file: Path,
    suite: EvalSuite,
    config: ResolvedConfig,
) -> SuiteResult:
    """Run a suite and return results. No reporting, no exit codes."""
    runner = SuiteRunner(eval_file, suite, config=config)
    return runner.run()
