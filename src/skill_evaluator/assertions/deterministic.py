"""Deterministic assertions: stop_reason, contains, regex, tool_called."""

from __future__ import annotations

import re
from typing import Any

from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
from skill_evaluator.config.schema import (
    OutputContainsAssertion,
    OutputMatchesRegexAssertion,
    OutputNotContainsAssertion,
    StopReasonAssertion,
    ToolCalledAssertion,
    ToolNotCalledAssertion,
)
from skill_evaluator.engine.trace import Trace


def check_stop_reason(assertion: StopReasonAssertion, trace: Trace) -> AssertionResult:
    actual = trace.stop_reason
    if actual == assertion.value:
        return AssertionResult(
            status=AssertionStatus.PASSED,
            assertion_type="stop_reason",
            message=f"Stop reason is '{actual}'",
        )
    return AssertionResult(
        status=AssertionStatus.FAILED,
        assertion_type="stop_reason",
        message=f"Expected stop reason '{assertion.value}', got '{actual}'",
    )


def check_output_contains(assertion: OutputContainsAssertion, trace: Trace) -> AssertionResult:
    text = trace.text_output
    if assertion.value in text:
        return AssertionResult(
            status=AssertionStatus.PASSED,
            assertion_type="output_contains",
            message=f"Output contains '{assertion.value}'",
        )
    details: dict[str, Any] = {"output": text[:500]}
    if len(text) > 500:
        details["truncated"] = True
        details["full_length"] = len(text)
    return AssertionResult(
        status=AssertionStatus.FAILED,
        assertion_type="output_contains",
        message=f"Output does not contain '{assertion.value}'",
        details=details,
    )


def check_output_not_contains(
    assertion: OutputNotContainsAssertion, trace: Trace
) -> AssertionResult:
    text = trace.text_output
    if assertion.value not in text:
        return AssertionResult(
            status=AssertionStatus.PASSED,
            assertion_type="output_not_contains",
            message=f"Output does not contain '{assertion.value}'",
        )
    details: dict[str, Any] = {"output": text[:500]}
    if len(text) > 500:
        details["truncated"] = True
        details["full_length"] = len(text)
    return AssertionResult(
        status=AssertionStatus.FAILED,
        assertion_type="output_not_contains",
        message=f"Output unexpectedly contains '{assertion.value}'",
        details=details,
    )


def check_output_matches_regex(
    assertion: OutputMatchesRegexAssertion, trace: Trace
) -> AssertionResult:
    text = trace.text_output
    if re.search(assertion.pattern, text):
        return AssertionResult(
            status=AssertionStatus.PASSED,
            assertion_type="output_matches_regex",
            message=f"Output matches pattern '{assertion.pattern}'",
        )
    details: dict[str, Any] = {"output": text[:500]}
    if len(text) > 500:
        details["truncated"] = True
        details["full_length"] = len(text)
    return AssertionResult(
        status=AssertionStatus.FAILED,
        assertion_type="output_matches_regex",
        message=f"Output does not match pattern '{assertion.pattern}'",
        details=details,
    )


def check_tool_called(assertion: ToolCalledAssertion, trace: Trace) -> AssertionResult:
    if assertion.tool in trace.tool_names:
        return AssertionResult(
            status=AssertionStatus.PASSED,
            assertion_type="tool_called",
            message=f"Tool '{assertion.tool}' was called",
        )
    return AssertionResult(
        status=AssertionStatus.FAILED,
        assertion_type="tool_called",
        message=f"Tool '{assertion.tool}' was not called",
        details={"tools_called": trace.tool_names},
    )


def check_tool_not_called(assertion: ToolNotCalledAssertion, trace: Trace) -> AssertionResult:
    if assertion.tool not in trace.tool_names:
        return AssertionResult(
            status=AssertionStatus.PASSED,
            assertion_type="tool_not_called",
            message=f"Tool '{assertion.tool}' was not called",
        )
    return AssertionResult(
        status=AssertionStatus.FAILED,
        assertion_type="tool_not_called",
        message=f"Tool '{assertion.tool}' was unexpectedly called",
        details={"tools_called": trace.tool_names},
    )
