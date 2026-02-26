"""Structured JSON report output."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from skill_evaluator.config.schema import EvalSuite
from skill_evaluator.reporting.console import SuiteResult


class JsonReporter:
    """Builds and writes a non-lossy JSON report from suite results."""

    def build_report(
        self, suite: EvalSuite, suite_result: SuiteResult, *, model: str | None = None
    ) -> dict[str, Any]:
        """Build the full JSON report dict."""
        # Per-test results (with optional per-run cost injection)
        tests = []
        for group in suite_result.test_results:
            group_dict = group.to_dict()
            if model:
                self._inject_run_costs(group_dict.get("runs", []), model)
                if "baseline_runs" in group_dict:
                    self._inject_run_costs(group_dict["baseline_runs"], model)
            tests.append(group_dict)

        # Aggregate token totals and duration
        total_input = 0
        total_output = 0
        total_cache_creation = 0
        total_cache_read = 0
        total_api_calls = 0
        total_duration = 0.0
        has_cache_data = False
        has_duration_data = False
        for group in suite_result.test_results:
            all_runs = list(group.runs)
            if group.baseline_runs:
                all_runs += group.baseline_runs
            for run in all_runs:
                if run.duration_seconds is not None:
                    total_duration += run.duration_seconds
                    has_duration_data = True
                if run.trace:
                    usage = run.trace.total_usage
                    total_input += usage.input_tokens
                    total_output += usage.output_tokens
                    total_api_calls += run.trace.turn_count
                    if usage.cache_creation_input_tokens is not None:
                        total_cache_creation += usage.cache_creation_input_tokens
                        has_cache_data = True
                    if usage.cache_read_input_tokens is not None:
                        total_cache_read += usage.cache_read_input_tokens
                        has_cache_data = True

        # Build defaults block
        defaults: dict[str, Any] = {
            "model": suite.defaults.model,
            "max_tokens": suite.defaults.max_tokens,
            "temperature": suite.defaults.temperature,
            "runs": suite.defaults.runs,
            "pass_threshold": suite.defaults.pass_threshold,
            "max_retries": suite.defaults.max_retries,
            "concurrency": suite.defaults.concurrency,
        }
        if suite.defaults.judge_model:
            defaults["judge_model"] = suite.defaults.judge_model
        if suite.defaults.system_prompt:
            defaults["system_prompt"] = suite.defaults.system_prompt

        # Build summary
        summary: dict[str, Any] = {
            "total_tests": len(suite_result.test_results),
            "passed_tests": suite_result.passed_count,
            "failed_tests": suite_result.failed_count,
            "all_passed": suite_result.all_passed,
            "total_api_calls": total_api_calls,
            "total_tokens": {
                "input_tokens": total_input,
                "output_tokens": total_output,
            },
        }
        if has_duration_data:
            summary["total_duration_seconds"] = round(total_duration, 3)

        # Cache summary
        if has_cache_data:
            summary["cache_summary"] = {
                "cache_creation_input_tokens": total_cache_creation,
                "cache_read_input_tokens": total_cache_read,
            }

        # Cost section — populated by the caller (cli.py) via inject_cost_data()

        report: dict[str, Any] = {
            "schema_version": "1",
            "suite": suite.suite,
            "skill": suite.skill,
            "defaults": defaults,
            "timestamp": datetime.now(UTC).isoformat(),
            "tests": tests,
            "summary": summary,
        }
        if suite_result.run_id:
            report["run_id"] = suite_result.run_id
        if suite_result.skill_file_hash:
            report["skill_file_hash"] = suite_result.skill_file_hash

        return report

    @staticmethod
    def _inject_run_costs(runs: list[dict], model: str) -> None:
        """Add cost_usd to each run dict that has trace data."""
        from skill_evaluator.engine.trace import TokenUsage
        from skill_evaluator.reporting.cost import estimate_cost

        for run_dict in runs:
            trace = run_dict.get("trace")
            if not trace or not trace.get("turns"):
                continue
            # Aggregate usage across turns
            total_input = 0
            total_output = 0
            total_cache_creation = 0
            total_cache_read = 0
            for turn in trace["turns"]:
                usage = turn.get("usage", {})
                total_input += usage.get("input_tokens", 0)
                total_output += usage.get("output_tokens", 0)
                total_cache_creation += usage.get("cache_creation_input_tokens", 0)
                total_cache_read += usage.get("cache_read_input_tokens", 0)
            token_usage = TokenUsage(
                input_tokens=total_input,
                output_tokens=total_output,
                cache_creation_input_tokens=total_cache_creation or None,
                cache_read_input_tokens=total_cache_read or None,
            )
            cost = estimate_cost(token_usage, model)
            if cost is not None:
                run_dict["cost_usd"] = round(cost, 6)

    def write(self, report: dict[str, Any], path: Path) -> None:
        """Write JSON report to file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
