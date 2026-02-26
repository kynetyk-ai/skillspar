"""LLM-as-judge assertion type."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from skill_evaluator.assertions.base import AssertionResult, AssertionStatus

if TYPE_CHECKING:
    from anthropic import Anthropic

    from skill_evaluator.config.schema import LLMJudgeAssertion
    from skill_evaluator.engine.trace import Trace

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "You are an evaluation judge. You will be given the output of an AI assistant "
    "and a set of criteria to evaluate against.\n\n"
    "Respond with PASS or FAIL on the FIRST line, followed by a brief explanation "
    "of your reasoning on subsequent lines.\n\n"
    "Example:\nPASS\nThe response correctly addresses the user's question."
)


def _build_judge_prompt(trace: Trace, criteria: str) -> str:
    """Build the user prompt for the judge model."""
    parts: list[str] = []

    parts.append("## Assistant Output\n")
    text = trace.text_output
    if text:
        parts.append(text)
    else:
        parts.append("(no text output)")

    tool_calls = trace.tool_calls
    if tool_calls:
        parts.append("\n## Tool Calls\n")
        for tc in tool_calls:
            parts.append(f"- {tc.name}({tc.input})")

    parts.append(f"\n## Criteria\n\n{criteria}")

    return "\n".join(parts)


def _parse_verdict(text: str) -> tuple[bool, str]:
    """Parse the judge response into (passed, reasoning).

    Returns ``(True, reasoning)`` for PASS, ``(False, reasoning)`` for FAIL.
    Raises ``ValueError`` if the verdict cannot be determined.
    """
    lines = text.strip().splitlines()
    if not lines:
        raise ValueError("Empty judge response")

    first_line = lines[0].strip().upper()
    reasoning = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

    if first_line.startswith("PASS"):
        return True, reasoning
    if first_line.startswith("FAIL"):
        return False, reasoning

    raise ValueError(f"Ambiguous verdict: {lines[0]!r}")


def check_llm_judge(
    assertion: LLMJudgeAssertion,
    trace: Trace,
    *,
    client: Anthropic,
    judge_model: str | None = None,
) -> AssertionResult:
    """Evaluate a trace against criteria using a second LLM call."""
    model = assertion.model or judge_model
    if not model:
        logger.warning("No model specified for LLM judge — returning error")
        return AssertionResult(
            status=AssertionStatus.ERROR,
            assertion_type="llm_judge",
            message="No model specified for LLM judge",
        )

    user_prompt = _build_judge_prompt(trace, assertion.criteria)
    logger.debug(
        "LLM judge: model=%s, criteria='%s', prompt_length=%d",
        model,
        assertion.criteria[:80],
        len(user_prompt),
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=512,
            temperature=0,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        logger.error("LLM judge API error: %s", e)
        return AssertionResult(
            status=AssertionStatus.ERROR,
            assertion_type="llm_judge",
            message=f"LLM judge API error: {e}",
        )

    response_text = ""
    for block in response.content:
        if block.type == "text":
            response_text += block.text

    try:
        passed, reasoning = _parse_verdict(response_text)
    except ValueError as e:
        return AssertionResult(
            status=AssertionStatus.ERROR,
            assertion_type="llm_judge",
            message=f"Could not parse judge verdict: {e}",
            details={"raw_response": response_text[:500]},
        )

    verdict_str = "PASS" if passed else "FAIL"
    reason_str = reasoning[:80] if reasoning else ""
    logger.debug("LLM judge verdict: %s, reasoning='%s'", verdict_str, reason_str)
    return AssertionResult(
        status=AssertionStatus.PASSED if passed else AssertionStatus.FAILED,
        assertion_type="llm_judge",
        message=reasoning or ("Passed" if passed else "Failed"),
    )
