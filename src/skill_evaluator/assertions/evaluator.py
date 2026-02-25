"""Assertion dispatch and result collection."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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
    LLMJudgeAssertion,
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

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from anthropic import Anthropic

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
    *,
    client: Anthropic | None = None,
    judge_model: str | None = None,
) -> list[AssertionResult]:
    """Evaluate a list of assertions against a trace.

    Returns one ``AssertionResult`` per assertion. Unimplemented assertion
    types return SKIPPED; exceptions during evaluation return ERROR.
    """
    logger.debug("Evaluating %d assertion(s)", len(assertions))
    results: list[AssertionResult] = []
    for assertion in assertions:
        # LLM judge requires special handling (needs API client)
        if isinstance(assertion, LLMJudgeAssertion):
            if client is not None:
                from skill_evaluator.assertions.llm_judge import check_llm_judge

                try:
                    result = check_llm_judge(
                        assertion, trace, client=client, judge_model=judge_model
                    )
                    results.append(result)
                except Exception as e:
                    results.append(AssertionResult(
                        status=AssertionStatus.ERROR,
                        assertion_type=assertion.type,
                        message=f"Error evaluating assertion: {e}",
                    ))
            else:
                results.append(AssertionResult(
                    status=AssertionStatus.SKIPPED,
                    assertion_type=assertion.type,
                    message="LLM judge requires an API client",
                ))
            continue

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
            logger.debug("Assertion %s: %s", assertion.type, result.status.value)
            results.append(result)
        except Exception as e:
            logger.debug("Assertion %s: ERROR (%s)", assertion.type, e)
            results.append(AssertionResult(
                status=AssertionStatus.ERROR,
                assertion_type=assertion.type,
                message=f"Error evaluating assertion: {e}",
            ))
    return results
