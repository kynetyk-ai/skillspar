"""MultiTurnExecutor — agentic loop with mock tool responses."""

from __future__ import annotations

import json
import logging
from typing import Any

from skill_evaluator.config.schema import InputConfig, ResolvedConfig, ToolResponseConfig
from skill_evaluator.engine.conversation import build_messages
from skill_evaluator.engine.trace import Trace, Turn
from skill_evaluator.providers.base import Provider, ProviderError
from skill_evaluator.tools.matcher import match_tool_response

logger = logging.getLogger(__name__)


def _serialize_tool_result(matched: dict[str, Any]) -> str:
    """Serialize a matched tool response for the API.

    If the response already has a plain string ``content`` key, return it
    directly.  Otherwise JSON-encode the whole dict so structured data
    round-trips correctly.
    """
    if isinstance(matched.get("content"), str):
        return matched["content"]
    return json.dumps(matched)


def _assistant_message_from_turn(turn: Turn) -> dict[str, Any]:
    """Rebuild the assistant message (canonical format) from a normalized Turn."""
    content: list[dict[str, Any]] = []
    if turn.text_output:
        content.append({"type": "text", "text": turn.text_output})
    for tc in turn.tool_calls:
        content.append(
            {
                "type": "tool_use",
                "id": tc.id,
                "name": tc.name,
                "input": tc.input,
            }
        )
    return {"role": "assistant", "content": content}


class MultiTurnExecutionError(Exception):
    """Raised when a multi-turn execution fails."""


class MultiTurnExecutor:
    """Executes an agentic loop: API call -> match tool calls -> inject responses -> repeat."""

    def __init__(
        self,
        provider: Provider,
        config: ResolvedConfig,
        tools: list[dict[str, Any]] | None = None,
        tool_responses: list[ToolResponseConfig] | None = None,
        max_turns: int = 10,
    ) -> None:
        self.provider = provider
        self.config = config
        self.tools = tools
        self.tool_responses = tool_responses or []
        self.max_turns = max_turns

    def execute(self, system_prompt: str | list[dict], input_config: InputConfig) -> Trace:
        """Run the agentic loop and return a Trace of all turns."""
        messages = build_messages(input_config.messages)
        trace = Trace()
        call_counts: dict[int, int] = {}

        logger.debug(
            "Multi-turn loop: model=%s, max_turns=%d, response_rules=%d",
            self.config.model,
            self.max_turns,
            len(self.tool_responses),
        )

        for turn_num in range(self.max_turns):
            try:
                turn = self.provider.create_message(
                    model=self.config.model,
                    system=system_prompt,
                    messages=messages,
                    tools=self.tools or None,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                )
            except ProviderError as e:
                logger.error("API call failed on turn %d: %s", turn_num, e)
                raise MultiTurnExecutionError(str(e)) from e

            trace.add_turn(turn)

            logger.debug(
                "Turn %d: stop_reason=%s, messages=%d, tool_calls=%d",
                turn_num,
                turn.stop_reason,
                len(messages),
                len(turn.tool_calls),
            )

            if turn.stop_reason != "tool_use":
                break

            messages.append(_assistant_message_from_turn(turn))

            # Match tool calls to scripted responses
            tool_result_blocks: list[dict[str, Any]] = []
            for tc in turn.tool_calls:
                matched = match_tool_response(tc, self.tool_responses, call_counts)
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": _serialize_tool_result(matched),
                    }
                )
            messages.append({"role": "user", "content": tool_result_blocks})

        logger.info("Multi-turn loop complete after %d turn(s)", len(trace.turns))
        return trace
