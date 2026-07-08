"""Tests for reporting/cost.py — opt-in cost estimation via SKILLSPAR_PRICING_FILE."""

import json

import pytest

from skill_evaluator.engine.trace import TokenUsage
from skill_evaluator.reporting.cost import (
    build_cost_summary,
    estimate_cache_savings,
    estimate_cost,
)

_SAMPLE_PRICING = {
    "sonnet-like": {
        "input": 3.00,
        "output": 15.00,
        "cache_write_multiplier": 1.25,
        "cache_read_multiplier": 0.1,
    },
    "haiku-like": {
        "input": 0.80,
        "output": 4.00,
    },
}


@pytest.fixture
def pricing_env(tmp_path, monkeypatch):
    """Opt into cost estimation with a sample pricing file."""
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text(json.dumps(_SAMPLE_PRICING))
    monkeypatch.setenv("SKILLSPAR_PRICING_FILE", str(pricing_file))
    return pricing_file


class TestOptIn:
    def test_no_pricing_file_returns_none(self, monkeypatch):
        monkeypatch.delenv("SKILLSPAR_PRICING_FILE", raising=False)
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)
        assert estimate_cost(usage, "claude-sonnet-4-5-20250929") is None

    def test_no_pricing_file_no_cache_savings(self, monkeypatch):
        monkeypatch.delenv("SKILLSPAR_PRICING_FILE", raising=False)
        assert estimate_cache_savings(1_000_000, "claude-sonnet-4-5-20250929") is None


class TestEstimateCost:
    def test_priced_model(self, pricing_env):
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)
        cost = estimate_cost(usage, "sonnet-like")
        assert cost is not None
        # 1M input * $3/M + 500K output * $15/M = $3 + $7.5 = $10.5
        assert cost == 10.5

    def test_model_missing_from_pricing_returns_none(self, pricing_env):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert estimate_cost(usage, "unknown-model") is None

    def test_cache_tokens(self, pricing_env):
        usage = TokenUsage(
            input_tokens=100_000,
            output_tokens=50_000,
            cache_creation_input_tokens=20_000,
            cache_read_input_tokens=80_000,
        )
        cost = estimate_cost(usage, "sonnet-like")
        assert cost is not None
        # input: 100K * $3/M = $0.30
        # output: 50K * $15/M = $0.75
        # cache write: 20K * $3/M * 1.25 = $0.075
        # cache read: 80K * $3/M * 0.1 = $0.024
        expected = 0.30 + 0.75 + 0.075 + 0.024
        assert abs(cost - expected) < 0.0001

    def test_multiplier_defaults(self, pricing_env):
        # haiku-like omits multipliers; defaults are 1.25 write / 0.1 read
        usage = TokenUsage(
            input_tokens=0,
            output_tokens=0,
            cache_creation_input_tokens=1_000_000,
            cache_read_input_tokens=1_000_000,
        )
        cost = estimate_cost(usage, "haiku-like")
        assert cost is not None
        expected = 0.80 * 1.25 + 0.80 * 0.1
        assert abs(cost - expected) < 0.0001

    def test_openai_cache_semantics(self, tmp_path, monkeypatch):
        pricing_file = tmp_path / "pricing.json"
        pricing_file.write_text(
            json.dumps(
                {
                    "gpt-like": {
                        "input": 2.0,
                        "output": 8.0,
                        "cache_read_multiplier": 0.5,
                        "cache_semantics": "openai",
                    }
                }
            )
        )
        monkeypatch.setenv("SKILLSPAR_PRICING_FILE", str(pricing_file))
        # 1000 input tokens, 400 of which are cached reads; 500 output
        usage = TokenUsage(input_tokens=1000, output_tokens=500, cache_read_input_tokens=400)
        cost = estimate_cost(usage, "gpt-like")
        expected = (600 * 2.0 + 400 * 2.0 * 0.5 + 500 * 8.0) / 1_000_000
        assert cost == pytest.approx(expected)


class TestEstimateCacheSavings:
    def test_priced_model(self, pricing_env):
        savings = estimate_cache_savings(1_000_000, "sonnet-like")
        assert savings is not None
        # 1M * $3/M * (1 - 0.1) = $2.70
        assert abs(savings - 2.7) < 0.0001

    def test_unpriced_model(self, pricing_env):
        assert estimate_cache_savings(1_000_000, "unknown") is None


class TestBuildCostSummary:
    def _suite_result(self):
        from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
        from skill_evaluator.engine.trace import Trace, Turn
        from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup

        trace = Trace()
        trace.add_turn(
            Turn(
                text_output="hi",
                tool_calls=[],
                stop_reason="end_turn",
                usage=TokenUsage(input_tokens=1000, output_tokens=500),
                raw_response=None,
            )
        )
        return SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(
                    test_name="t",
                    runs=[
                        TestResult(
                            test_name="t",
                            assertion_results=[
                                AssertionResult(
                                    status=AssertionStatus.PASSED, assertion_type="x", message="ok"
                                ),
                            ],
                            trace=trace,
                        )
                    ],
                )
            ],
        )

    def test_with_traces(self, pricing_env):
        summary = build_cost_summary(self._suite_result(), "sonnet-like")
        assert summary is not None
        assert "total_cost_usd" in summary
        assert "skill_cost_usd" in summary
        assert summary["total_cost_usd"] > 0

    def test_without_pricing_returns_none(self, monkeypatch):
        monkeypatch.delenv("SKILLSPAR_PRICING_FILE", raising=False)
        assert build_cost_summary(self._suite_result(), "sonnet-like") is None

    def test_unpriced_model_returns_none(self, pricing_env):
        from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup

        result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(test_name="t", runs=[TestResult(test_name="t")]),
            ],
        )
        assert build_cost_summary(result, "unknown-model") is None
