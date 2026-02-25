"""Tests for reporting/cost.py — cost estimation."""

import json
from unittest.mock import patch

from skill_evaluator.engine.trace import TokenUsage
from skill_evaluator.reporting.cost import (
    build_cost_summary,
    estimate_cache_savings,
    estimate_cost,
)


class TestEstimateCost:
    def test_known_model(self):
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)
        cost = estimate_cost(usage, "claude-sonnet-4-5-20250929")
        assert cost is not None
        # 1M input * $3/M + 500K output * $15/M = $3 + $7.5 = $10.5
        assert cost == 10.5

    def test_unknown_model_returns_none(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        cost = estimate_cost(usage, "unknown-model")
        assert cost is None

    def test_cache_tokens(self):
        usage = TokenUsage(
            input_tokens=100_000,
            output_tokens=50_000,
            cache_creation_input_tokens=20_000,
            cache_read_input_tokens=80_000,
        )
        cost = estimate_cost(usage, "claude-sonnet-4-5-20250929")
        assert cost is not None
        # input: 100K * $3/M = $0.30
        # output: 50K * $15/M = $0.75
        # cache write: 20K * $3/M * 1.25 = $0.075
        # cache read: 80K * $3/M * 0.1 = $0.024
        expected = 0.30 + 0.75 + 0.075 + 0.024
        assert abs(cost - expected) < 0.0001

    def test_haiku_pricing(self):
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = estimate_cost(usage, "claude-haiku-4-5-20251001")
        assert cost is not None
        # $0.80 + $4.00 = $4.80
        assert cost == 4.8

    def test_opus_pricing(self):
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = estimate_cost(usage, "claude-opus-4-20250514")
        assert cost is not None
        # $15.00 + $75.00 = $90.00
        assert cost == 90.0

    def test_custom_pricing_file(self, tmp_path):
        pricing_file = tmp_path / "pricing.json"
        pricing_file.write_text(json.dumps({
            "custom-model": {
                "input": 1.0,
                "output": 2.0,
                "cache_write_multiplier": 1.5,
                "cache_read_multiplier": 0.2,
            }
        }))
        with patch.dict("os.environ", {"SKILLSPAR_PRICING_FILE": str(pricing_file)}):
            usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
            cost = estimate_cost(usage, "custom-model")
            assert cost is not None
            # $1.0 + $2.0 = $3.0
            assert cost == 3.0

    def test_custom_pricing_overrides_builtin(self, tmp_path):
        pricing_file = tmp_path / "pricing.json"
        pricing_file.write_text(json.dumps({
            "claude-sonnet-4-5-20250929": {
                "input": 100.0,
                "output": 200.0,
            }
        }))
        with patch.dict("os.environ", {"SKILLSPAR_PRICING_FILE": str(pricing_file)}):
            usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
            cost = estimate_cost(usage, "claude-sonnet-4-5-20250929")
            assert cost is not None
            assert cost == 300.0


class TestEstimateCacheSavings:
    def test_known_model(self):
        savings = estimate_cache_savings(1_000_000, "claude-sonnet-4-5-20250929")
        assert savings is not None
        # 1M * $3/M * (1 - 0.1) = $2.70
        assert abs(savings - 2.7) < 0.0001

    def test_unknown_model(self):
        assert estimate_cache_savings(1_000_000, "unknown") is None


class TestBuildCostSummary:
    def test_with_traces(self):
        from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
        from skill_evaluator.engine.trace import Trace, Turn
        from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup

        trace = Trace()
        trace.add_turn(Turn(
            text_output="hi",
            tool_calls=[],
            stop_reason="end_turn",
            usage=TokenUsage(input_tokens=1000, output_tokens=500),
            raw_response=None,
        ))
        result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(
                    test_name="t",
                    runs=[
                        TestResult(
                            test_name="t",
                            assertion_results=[
                                AssertionResult(status=AssertionStatus.PASSED, assertion_type="x", message="ok"),
                            ],
                            trace=trace,
                        )
                    ],
                )
            ],
        )
        summary = build_cost_summary(result, "claude-sonnet-4-5-20250929")
        assert summary is not None
        assert "total_cost_usd" in summary
        assert "skill_cost_usd" in summary
        assert summary["total_cost_usd"] > 0

    def test_unknown_model_returns_none(self):
        from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup

        result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(test_name="t", runs=[TestResult(test_name="t")]),
            ],
        )
        assert build_cost_summary(result, "unknown-model") is None
