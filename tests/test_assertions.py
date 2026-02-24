"""Tests for assertions/deterministic.py — assertion functions."""

from skill_evaluator.assertions.base import AssertionStatus
from skill_evaluator.assertions.deterministic import (
    check_output_contains,
    check_output_matches_regex,
    check_output_not_contains,
    check_stop_reason,
    check_tool_called,
    check_tool_not_called,
)
from skill_evaluator.config.schema import (
    OutputContainsAssertion,
    OutputMatchesRegexAssertion,
    OutputNotContainsAssertion,
    StopReasonAssertion,
    ToolCalledAssertion,
    ToolNotCalledAssertion,
)


class TestStopReason:
    def test_pass(self, simple_text_trace):
        a = StopReasonAssertion(type="stop_reason", value="end_turn")
        result = check_stop_reason(a, simple_text_trace)
        assert result.status == AssertionStatus.PASSED

    def test_fail(self, simple_text_trace):
        a = StopReasonAssertion(type="stop_reason", value="tool_use")
        result = check_stop_reason(a, simple_text_trace)
        assert result.status == AssertionStatus.FAILED


class TestOutputContains:
    def test_pass(self, simple_text_trace):
        a = OutputContainsAssertion(type="output_contains", value="Alice")
        result = check_output_contains(a, simple_text_trace)
        assert result.status == AssertionStatus.PASSED

    def test_fail(self, simple_text_trace):
        a = OutputContainsAssertion(type="output_contains", value="Bob")
        result = check_output_contains(a, simple_text_trace)
        assert result.status == AssertionStatus.FAILED


class TestOutputNotContains:
    def test_pass(self, simple_text_trace):
        a = OutputNotContainsAssertion(type="output_not_contains", value="Bob")
        result = check_output_not_contains(a, simple_text_trace)
        assert result.status == AssertionStatus.PASSED

    def test_fail(self, simple_text_trace):
        a = OutputNotContainsAssertion(type="output_not_contains", value="Alice")
        result = check_output_not_contains(a, simple_text_trace)
        assert result.status == AssertionStatus.FAILED


class TestOutputMatchesRegex:
    def test_pass(self, simple_text_trace):
        a = OutputMatchesRegexAssertion(type="output_matches_regex", pattern="(?i)hello")
        result = check_output_matches_regex(a, simple_text_trace)
        assert result.status == AssertionStatus.PASSED

    def test_fail(self, simple_text_trace):
        a = OutputMatchesRegexAssertion(type="output_matches_regex", pattern="^goodbye$")
        result = check_output_matches_regex(a, simple_text_trace)
        assert result.status == AssertionStatus.FAILED


class TestToolCalled:
    def test_pass(self, tool_call_trace):
        a = ToolCalledAssertion(type="tool_called", tool="Write")
        result = check_tool_called(a, tool_call_trace)
        assert result.status == AssertionStatus.PASSED

    def test_fail(self, tool_call_trace):
        a = ToolCalledAssertion(type="tool_called", tool="Read")
        result = check_tool_called(a, tool_call_trace)
        assert result.status == AssertionStatus.FAILED


class TestToolNotCalled:
    def test_pass(self, tool_call_trace):
        a = ToolNotCalledAssertion(type="tool_not_called", tool="Read")
        result = check_tool_not_called(a, tool_call_trace)
        assert result.status == AssertionStatus.PASSED

    def test_fail(self, tool_call_trace):
        a = ToolNotCalledAssertion(type="tool_not_called", tool="Write")
        result = check_tool_not_called(a, tool_call_trace)
        assert result.status == AssertionStatus.FAILED
