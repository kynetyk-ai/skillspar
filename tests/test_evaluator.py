"""Tests for assertions/evaluator.py — dispatch and error handling."""

from skill_evaluator.assertions.base import AssertionStatus
from skill_evaluator.assertions.evaluator import evaluate_assertions
from skill_evaluator.config.schema import (
    LLMJudgeAssertion,
    OutputContainsAssertion,
    StopReasonAssertion,
    ToolSequenceAssertion,
)
from skill_evaluator.providers.anthropic import AnthropicProvider


class TestEvaluateAssertions:
    def test_dispatches_to_handler(self, simple_text_trace):
        assertions = [
            StopReasonAssertion(type="stop_reason", value="end_turn"),
            OutputContainsAssertion(type="output_contains", value="Alice"),
        ]
        results = evaluate_assertions(assertions, simple_text_trace)
        assert len(results) == 2
        assert all(r.status == AssertionStatus.PASSED for r in results)

    def test_skips_unimplemented_types(self, simple_text_trace):
        """LLM judge without client is SKIPPED."""
        assertions = [
            LLMJudgeAssertion(type="llm_judge", criteria="Is the response friendly?"),
        ]
        results = evaluate_assertions(assertions, simple_text_trace)
        assert len(results) == 1
        assert results[0].status == AssertionStatus.SKIPPED

    def test_llm_judge_skipped_without_client(self, simple_text_trace):
        assertions = [
            LLMJudgeAssertion(type="llm_judge", criteria="Is the response friendly?"),
        ]
        results = evaluate_assertions(assertions, simple_text_trace, judge_provider=None)
        assert results[0].status == AssertionStatus.SKIPPED

    def test_llm_judge_dispatches(
        self, simple_text_trace, mock_anthropic_client, mock_anthropic_message
    ):
        """LLM judge with client dispatches and returns PASSED."""
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="PASS\nGreat response."
        )

        assertions = [
            LLMJudgeAssertion(type="llm_judge", criteria="Is it friendly?"),
        ]
        results = evaluate_assertions(
            assertions,
            simple_text_trace,
            judge_provider=AnthropicProvider(mock_anthropic_client),
            judge_model="claude-haiku-3",
        )
        assert len(results) == 1
        assert results[0].status == AssertionStatus.PASSED

    def test_llm_judge_fails(
        self, simple_text_trace, mock_anthropic_client, mock_anthropic_message
    ):
        """LLM judge returns FAILED when judge says FAIL."""
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="FAIL\nNot detailed enough."
        )

        assertions = [
            LLMJudgeAssertion(type="llm_judge", criteria="Is it detailed?"),
        ]
        results = evaluate_assertions(
            assertions,
            simple_text_trace,
            judge_provider=AnthropicProvider(mock_anthropic_client),
            judge_model="claude-haiku-3",
        )
        assert len(results) == 1
        assert results[0].status == AssertionStatus.FAILED

    def test_mixed_results(self, simple_text_trace):
        assertions = [
            StopReasonAssertion(type="stop_reason", value="end_turn"),
            OutputContainsAssertion(type="output_contains", value="NOTFOUND"),
        ]
        results = evaluate_assertions(assertions, simple_text_trace)
        assert results[0].status == AssertionStatus.PASSED
        assert results[1].status == AssertionStatus.FAILED

    def test_tool_sequence_dispatches(self, multi_turn_trace):
        assertions = [
            ToolSequenceAssertion(type="tool_sequence", tools=["Read", "Write"]),
        ]
        results = evaluate_assertions(assertions, multi_turn_trace)
        assert len(results) == 1
        assert results[0].status == AssertionStatus.PASSED

    def test_tool_sequence_fails(self, multi_turn_trace):
        assertions = [
            ToolSequenceAssertion(type="tool_sequence", tools=["Write", "Read"]),
        ]
        results = evaluate_assertions(assertions, multi_turn_trace)
        assert results[0].status == AssertionStatus.FAILED
