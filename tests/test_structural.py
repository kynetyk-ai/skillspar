"""Tests for assertions/structural.py — structural assertion handlers."""

import pytest

from skill_evaluator.assertions.base import AssertionStatus
from skill_evaluator.assertions.structural import (
    check_tool_args_match,
    check_tool_called_times,
    check_tool_sequence,
    check_turn_count,
)
from skill_evaluator.config.schema import (
    ToolArgsMatchAssertion,
    ToolCalledTimesAssertion,
    ToolSequenceAssertion,
    TurnCountAssertion,
)


class TestToolCalledTimes:
    def test_exactly_pass(self, multi_turn_trace):
        a = ToolCalledTimesAssertion(type="tool_called_times", tool="Read", exactly=1)
        result = check_tool_called_times(a, multi_turn_trace)
        assert result.status == AssertionStatus.PASSED

    def test_exactly_fail(self, multi_turn_trace):
        a = ToolCalledTimesAssertion(type="tool_called_times", tool="Read", exactly=2)
        result = check_tool_called_times(a, multi_turn_trace)
        assert result.status == AssertionStatus.FAILED

    def test_min_pass(self, multi_turn_trace):
        a = ToolCalledTimesAssertion(type="tool_called_times", tool="Read", min=1)
        result = check_tool_called_times(a, multi_turn_trace)
        assert result.status == AssertionStatus.PASSED

    def test_min_fail(self, multi_turn_trace):
        a = ToolCalledTimesAssertion(type="tool_called_times", tool="Read", min=3)
        result = check_tool_called_times(a, multi_turn_trace)
        assert result.status == AssertionStatus.FAILED

    def test_max_pass(self, multi_turn_trace):
        a = ToolCalledTimesAssertion(type="tool_called_times", tool="Read", max=2)
        result = check_tool_called_times(a, multi_turn_trace)
        assert result.status == AssertionStatus.PASSED

    def test_max_fail(self, multi_turn_trace):
        a = ToolCalledTimesAssertion(type="tool_called_times", tool="Write", max=0)
        result = check_tool_called_times(a, multi_turn_trace)
        assert result.status == AssertionStatus.FAILED

    def test_uncalled_tool_exactly_zero(self, multi_turn_trace):
        a = ToolCalledTimesAssertion(type="tool_called_times", tool="Bash", exactly=0)
        result = check_tool_called_times(a, multi_turn_trace)
        assert result.status == AssertionStatus.PASSED


class TestToolArgsMatch:
    def test_pass(self, multi_turn_trace):
        a = ToolArgsMatchAssertion(
            type="tool_args_match",
            tool="Read",
            path="$.file_path",
            pattern="hello\\.txt$",
        )
        result = check_tool_args_match(a, multi_turn_trace)
        assert result.status == AssertionStatus.PASSED

    def test_fail_pattern(self, multi_turn_trace):
        a = ToolArgsMatchAssertion(
            type="tool_args_match",
            tool="Read",
            path="$.file_path",
            pattern="goodbye\\.txt$",
        )
        result = check_tool_args_match(a, multi_turn_trace)
        assert result.status == AssertionStatus.FAILED

    def test_fail_tool_not_called(self, multi_turn_trace):
        a = ToolArgsMatchAssertion(
            type="tool_args_match",
            tool="Bash",
            path="$.command",
            pattern="ls",
        )
        result = check_tool_args_match(a, multi_turn_trace)
        assert result.status == AssertionStatus.FAILED

    def test_write_content_match(self, multi_turn_trace):
        a = ToolArgsMatchAssertion(
            type="tool_args_match",
            tool="Write",
            path="$.content",
            pattern="updated",
        )
        result = check_tool_args_match(a, multi_turn_trace)
        assert result.status == AssertionStatus.PASSED


class TestToolSequence:
    def test_pass(self, multi_turn_trace):
        a = ToolSequenceAssertion(type="tool_sequence", tools=["Read", "Write"])
        result = check_tool_sequence(a, multi_turn_trace)
        assert result.status == AssertionStatus.PASSED

    def test_fail_wrong_order(self, multi_turn_trace):
        a = ToolSequenceAssertion(type="tool_sequence", tools=["Write", "Read"])
        result = check_tool_sequence(a, multi_turn_trace)
        assert result.status == AssertionStatus.FAILED

    def test_pass_single_tool(self, multi_turn_trace):
        a = ToolSequenceAssertion(type="tool_sequence", tools=["Read"])
        result = check_tool_sequence(a, multi_turn_trace)
        assert result.status == AssertionStatus.PASSED

    def test_fail_missing_tool(self, multi_turn_trace):
        a = ToolSequenceAssertion(type="tool_sequence", tools=["Bash"])
        result = check_tool_sequence(a, multi_turn_trace)
        assert result.status == AssertionStatus.FAILED

    def test_pass_empty_sequence(self, multi_turn_trace):
        a = ToolSequenceAssertion(type="tool_sequence", tools=[])
        result = check_tool_sequence(a, multi_turn_trace)
        assert result.status == AssertionStatus.PASSED


class TestTurnCount:
    def test_exactly_pass(self, multi_turn_trace):
        a = TurnCountAssertion(type="turn_count", exactly=3)
        result = check_turn_count(a, multi_turn_trace)
        assert result.status == AssertionStatus.PASSED

    def test_exactly_fail(self, multi_turn_trace):
        a = TurnCountAssertion(type="turn_count", exactly=2)
        result = check_turn_count(a, multi_turn_trace)
        assert result.status == AssertionStatus.FAILED

    def test_min_pass(self, multi_turn_trace):
        a = TurnCountAssertion(type="turn_count", min=2)
        result = check_turn_count(a, multi_turn_trace)
        assert result.status == AssertionStatus.PASSED

    def test_min_fail(self, multi_turn_trace):
        a = TurnCountAssertion(type="turn_count", min=5)
        result = check_turn_count(a, multi_turn_trace)
        assert result.status == AssertionStatus.FAILED

    def test_max_pass(self, multi_turn_trace):
        a = TurnCountAssertion(type="turn_count", max=5)
        result = check_turn_count(a, multi_turn_trace)
        assert result.status == AssertionStatus.PASSED

    def test_max_fail(self, multi_turn_trace):
        a = TurnCountAssertion(type="turn_count", max=2)
        result = check_turn_count(a, multi_turn_trace)
        assert result.status == AssertionStatus.FAILED

    def test_no_constraints_rejected(self):
        with pytest.raises(ValueError, match="At least one of"):
            TurnCountAssertion(type="turn_count")
