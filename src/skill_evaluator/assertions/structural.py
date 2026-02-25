"""Structural assertions: tool_called_times, tool_args_match, tool_sequence, turn_count."""

from __future__ import annotations

import re

from jsonpath_ng import parse as jsonpath_parse

from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
from skill_evaluator.config.schema import (
    ToolArgsMatchAssertion,
    ToolCalledTimesAssertion,
    ToolSequenceAssertion,
    TurnCountAssertion,
)
from skill_evaluator.engine.trace import Trace


def check_tool_called_times(
    assertion: ToolCalledTimesAssertion, trace: Trace
) -> AssertionResult:
    count = trace.tool_names.count(assertion.tool)

    if assertion.exactly is not None:
        if count == assertion.exactly:
            return AssertionResult(
                status=AssertionStatus.PASSED,
                assertion_type="tool_called_times",
                message=f"Tool '{assertion.tool}' called exactly {count} time(s)",
            )
        return AssertionResult(
            status=AssertionStatus.FAILED,
            assertion_type="tool_called_times",
            message=(
                f"Expected '{assertion.tool}' called exactly {assertion.exactly} "
                f"time(s), got {count}"
            ),
            details={"tool": assertion.tool, "expected": assertion.exactly, "actual": count},
        )

    # Check min/max bounds
    if assertion.min is not None and count < assertion.min:
        return AssertionResult(
            status=AssertionStatus.FAILED,
            assertion_type="tool_called_times",
            message=(
                f"Expected '{assertion.tool}' called at least {assertion.min} "
                f"time(s), got {count}"
            ),
            details={"tool": assertion.tool, "min": assertion.min, "actual": count},
        )
    if assertion.max is not None and count > assertion.max:
        return AssertionResult(
            status=AssertionStatus.FAILED,
            assertion_type="tool_called_times",
            message=(
                f"Expected '{assertion.tool}' called at most {assertion.max} "
                f"time(s), got {count}"
            ),
            details={"tool": assertion.tool, "max": assertion.max, "actual": count},
        )

    return AssertionResult(
        status=AssertionStatus.PASSED,
        assertion_type="tool_called_times",
        message=f"Tool '{assertion.tool}' called {count} time(s)",
    )


def check_tool_args_match(
    assertion: ToolArgsMatchAssertion, trace: Trace
) -> AssertionResult:
    matching_calls = [tc for tc in trace.tool_calls if tc.name == assertion.tool]
    if not matching_calls:
        return AssertionResult(
            status=AssertionStatus.FAILED,
            assertion_type="tool_args_match",
            message=f"Tool '{assertion.tool}' was not called",
            details={"tools_called": trace.tool_names},
        )

    expr = jsonpath_parse(assertion.path)
    for tc in matching_calls:
        matches = expr.find(tc.input)
        for match in matches:
            if re.search(assertion.pattern, str(match.value)):
                return AssertionResult(
                    status=AssertionStatus.PASSED,
                    assertion_type="tool_args_match",
                    message=(
                        f"Tool '{assertion.tool}' arg at '{assertion.path}' "
                        f"matches '{assertion.pattern}'"
                    ),
                )

    return AssertionResult(
        status=AssertionStatus.FAILED,
        assertion_type="tool_args_match",
        message=(
            f"No call to '{assertion.tool}' has arg at '{assertion.path}' "
            f"matching '{assertion.pattern}'"
        ),
        details={
            "tool": assertion.tool,
            "path": assertion.path,
            "pattern": assertion.pattern,
            "calls_checked": len(matching_calls),
        },
    )


def check_tool_sequence(
    assertion: ToolSequenceAssertion, trace: Trace
) -> AssertionResult:
    """Check that expected tools appear as a subsequence of actual tool names."""
    actual = trace.tool_names
    expected = assertion.tools
    idx = 0
    for name in actual:
        if idx < len(expected) and name == expected[idx]:
            idx += 1
    if idx == len(expected):
        return AssertionResult(
            status=AssertionStatus.PASSED,
            assertion_type="tool_sequence",
            message=f"Tool sequence {expected} found",
        )
    return AssertionResult(
        status=AssertionStatus.FAILED,
        assertion_type="tool_sequence",
        message=f"Expected tool sequence {expected}, got {actual}",
        details={"expected": expected, "actual": actual, "matched_up_to": idx},
    )


def check_turn_count(
    assertion: TurnCountAssertion, trace: Trace
) -> AssertionResult:
    count = trace.turn_count

    if assertion.exactly is not None:
        if count == assertion.exactly:
            return AssertionResult(
                status=AssertionStatus.PASSED,
                assertion_type="turn_count",
                message=f"Turn count is exactly {count}",
            )
        return AssertionResult(
            status=AssertionStatus.FAILED,
            assertion_type="turn_count",
            message=f"Expected exactly {assertion.exactly} turn(s), got {count}",
            details={"expected": assertion.exactly, "actual": count},
        )

    if assertion.min is not None and count < assertion.min:
        return AssertionResult(
            status=AssertionStatus.FAILED,
            assertion_type="turn_count",
            message=f"Expected at least {assertion.min} turn(s), got {count}",
            details={"min": assertion.min, "actual": count},
        )
    if assertion.max is not None and count > assertion.max:
        return AssertionResult(
            status=AssertionStatus.FAILED,
            assertion_type="turn_count",
            message=f"Expected at most {assertion.max} turn(s), got {count}",
            details={"max": assertion.max, "actual": count},
        )

    return AssertionResult(
        status=AssertionStatus.PASSED,
        assertion_type="turn_count",
        message=f"Turn count is {count}",
    )
