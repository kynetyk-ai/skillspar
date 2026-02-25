"""Assertion dispatch and result collection."""

from __future__ import annotations

from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
from skill_evaluator.assertions.deterministic import (
    check_output_contains,
    check_output_matches_regex,
    check_output_not_contains,
    check_stop_reason,
    check_tool_called,
    check_tool_not_called,
)
from skill_evaluator.assertions.structural import (
    check_tool_args_match,
    check_tool_called_times,
    check_tool_sequence,
    check_turn_count,
)
from skill_evaluator.config.schema import (
    AssertionConfig,
    OutputContainsAssertion,
    OutputMatchesRegexAssertion,
    OutputNotContainsAssertion,
    StopReasonAssertion,
    ToolArgsMatchAssertion,
    ToolCalledAssertion,
    ToolCalledTimesAssertion,
    ToolNotCalledAssertion,
    ToolSequenceAssertion,
    TurnCountAssertion,
)
from skill_evaluator.engine.trace import Trace

_HANDLERS: dict = {
    StopReasonAssertion: check_stop_reason,
    OutputContainsAssertion: check_output_contains,
    OutputNotContainsAssertion: check_output_not_contains,
    OutputMatchesRegexAssertion: check_output_matches_regex,
    ToolCalledAssertion: check_tool_called,
    ToolNotCalledAssertion: check_tool_not_called,
    ToolCalledTimesAssertion: check_tool_called_times,
    ToolArgsMatchAssertion: check_tool_args_match,
    ToolSequenceAssertion: check_tool_sequence,
    TurnCountAssertion: check_turn_count,
}


def evaluate_assertions(
    assertions: list[AssertionConfig],
    trace: Trace,
) -> list[AssertionResult]:
    """Evaluate a list of assertions against a trace.

    Returns one ``AssertionResult`` per assertion. Unimplemented assertion
    types return SKIPPED; exceptions during evaluation return ERROR.
    """
    results: list[AssertionResult] = []
    for assertion in assertions:
        handler = _HANDLERS.get(type(assertion))
        if handler is None:
            results.append(AssertionResult(
                status=AssertionStatus.SKIPPED,
                assertion_type=assertion.type,
                message=f"Assertion type '{assertion.type}' not yet implemented",
            ))
            continue
        try:
            result = handler(assertion, trace)
            results.append(result)
        except Exception as e:
            results.append(AssertionResult(
                status=AssertionStatus.ERROR,
                assertion_type=assertion.type,
                message=f"Error evaluating assertion: {e}",
            ))
    return results
