"""Tests for assertions/llm_judge.py — LLM-as-judge handler."""

from skill_evaluator.assertions.base import AssertionStatus
from skill_evaluator.assertions.llm_judge import (
    _parse_verdict,
    check_llm_judge,
)
from skill_evaluator.config.schema import LLMJudgeAssertion


class TestParseVerdict:
    def test_pass_verdict(self):
        passed, reasoning = _parse_verdict("PASS\nLooks good.")
        assert passed is True
        assert reasoning == "Looks good."

    def test_fail_verdict(self):
        passed, reasoning = _parse_verdict("FAIL\nDoes not meet criteria.")
        assert passed is False
        assert reasoning == "Does not meet criteria."

    def test_case_insensitive(self):
        passed, _ = _parse_verdict("pass\nOK")
        assert passed is True

    def test_pass_no_reasoning(self):
        passed, reasoning = _parse_verdict("PASS")
        assert passed is True
        assert reasoning == ""

    def test_ambiguous_verdict_raises(self):
        import pytest

        with pytest.raises(ValueError, match="Ambiguous verdict"):
            _parse_verdict("MAYBE\nNot sure.")

    def test_empty_response_raises(self):
        import pytest

        with pytest.raises(ValueError, match="Empty judge response"):
            _parse_verdict("")


class TestCheckLlmJudge:
    def test_pass_result(self, simple_text_trace, mock_anthropic_client, mock_anthropic_message):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="PASS\nThe response is friendly."
        )

        assertion = LLMJudgeAssertion(type="llm_judge", criteria="Is it friendly?")
        result = check_llm_judge(
            assertion,
            simple_text_trace,
            client=mock_anthropic_client,
            judge_model="claude-haiku-3",
        )

        assert result.status == AssertionStatus.PASSED
        assert result.assertion_type == "llm_judge"
        assert "friendly" in result.message

    def test_fail_result(self, simple_text_trace, mock_anthropic_client, mock_anthropic_message):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="FAIL\nThe response lacks detail."
        )

        assertion = LLMJudgeAssertion(type="llm_judge", criteria="Is it detailed?")
        result = check_llm_judge(
            assertion,
            simple_text_trace,
            client=mock_anthropic_client,
            judge_model="claude-haiku-3",
        )

        assert result.status == AssertionStatus.FAILED
        assert "detail" in result.message

    def test_ambiguous_verdict_returns_error(
        self, simple_text_trace, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="MAYBE\nI'm not sure."
        )

        assertion = LLMJudgeAssertion(type="llm_judge", criteria="Is it good?")
        result = check_llm_judge(
            assertion,
            simple_text_trace,
            client=mock_anthropic_client,
            judge_model="claude-haiku-3",
        )

        assert result.status == AssertionStatus.ERROR
        assert "verdict" in result.message.lower()

    def test_api_error_returns_error(self, simple_text_trace, mock_anthropic_client):
        mock_anthropic_client.messages.create.side_effect = Exception("API timeout")

        assertion = LLMJudgeAssertion(type="llm_judge", criteria="Is it good?")
        result = check_llm_judge(
            assertion,
            simple_text_trace,
            client=mock_anthropic_client,
            judge_model="claude-haiku-3",
        )

        assert result.status == AssertionStatus.ERROR
        assert "API" in result.message

    def test_custom_model_override(
        self, simple_text_trace, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="PASS\nOK"
        )

        assertion = LLMJudgeAssertion(
            type="llm_judge", criteria="Is it good?", model="claude-opus-4"
        )
        check_llm_judge(
            assertion,
            simple_text_trace,
            client=mock_anthropic_client,
            judge_model="claude-haiku-3",
        )

        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4"

    def test_falls_back_to_judge_model(
        self, simple_text_trace, mock_anthropic_client, mock_anthropic_message
    ):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="PASS\nOK"
        )

        assertion = LLMJudgeAssertion(type="llm_judge", criteria="Is it good?")
        check_llm_judge(
            assertion,
            simple_text_trace,
            client=mock_anthropic_client,
            judge_model="claude-haiku-3",
        )

        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-3"

    def test_no_model_returns_error(self, simple_text_trace, mock_anthropic_client):
        assertion = LLMJudgeAssertion(type="llm_judge", criteria="Is it good?")
        result = check_llm_judge(
            assertion,
            simple_text_trace,
            client=mock_anthropic_client,
            judge_model=None,
        )

        assert result.status == AssertionStatus.ERROR
        assert "No model" in result.message
