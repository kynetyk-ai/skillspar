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
from skill_evaluator.config.schema import (
    AssertionConfig,
    OutputContainsAssertion,
    OutputMatchesRegexAssertion,
    OutputNotContainsAssertion,
    StopReasonAssertion,
    ToolCalledAssertion,
    ToolNotCalledAssertion,
)
from skill_evaluator.engine.trace import Trace

_HANDLERS: dict = {
    StopReasonAssertion: check_stop_reason,
    OutputContainsAssertion: check_output_contains,
    OutputNotContainsAssertion: check_output_not_contains,
    OutputMatchesRegexAssertion: check_output_matches_regex,
    ToolCalledAssertion: check_tool_called,
    ToolNotCalledAssertion: check_tool_not_called,
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
