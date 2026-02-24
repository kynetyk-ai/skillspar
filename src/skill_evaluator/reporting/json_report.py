"""Structured JSON report output."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skill_evaluator.config.schema import EvalSuite
from skill_evaluator.reporting.console import SuiteResult


class JsonReporter:
    """Builds and writes a non-lossy JSON report from suite results."""

    def build_report(self, suite: EvalSuite, suite_result: SuiteResult) -> dict[str, Any]:
        """Build the full JSON report dict."""
        # Per-test results
        tests = [group.to_dict() for group in suite_result.test_results]

        # Aggregate token totals
        total_input = 0
        total_output = 0
        total_api_calls = 0
        for group in suite_result.test_results:
            for run in group.runs:
                if run.trace:
                    usage = run.trace.total_usage
                    total_input += usage.input_tokens
                    total_output += usage.output_tokens
                    total_api_calls += run.trace.turn_count
            if group.baseline_runs:
                for run in group.baseline_runs:
                    if run.trace:
                        usage = run.trace.total_usage
                        total_input += usage.input_tokens
                        total_output += usage.output_tokens
                        total_api_calls += run.trace.turn_count

        return {
            "suite": suite.suite,
            "skill": suite.skill,
            "defaults": {
                "model": suite.defaults.model,
                "max_tokens": suite.defaults.max_tokens,
                "temperature": suite.defaults.temperature,
                "runs": suite.defaults.runs,
                "pass_threshold": suite.defaults.pass_threshold,
                "max_retries": suite.defaults.max_retries,
                "concurrency": suite.defaults.concurrency,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tests": tests,
            "summary": {
                "total_tests": len(suite_result.test_results),
                "passed_tests": suite_result.passed_count,
                "failed_tests": suite_result.failed_count,
                "all_passed": suite_result.all_passed,
                "total_api_calls": total_api_calls,
                "total_tokens": {
                    "input_tokens": total_input,
                    "output_tokens": total_output,
                },
            },
        }

    def write(self, report: dict[str, Any], path: Path) -> None:
        """Write JSON report to file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
