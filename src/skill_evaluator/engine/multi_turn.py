"""MultiTurnExecutor — agentic loop with mock tool responses."""

from __future__ import annotations

import json
import logging
from typing import Any

from anthropic import Anthropic

from skill_evaluator.config.schema import InputConfig, SuiteDefaults, ToolResponseConfig
from skill_evaluator.engine.conversation import build_messages
from skill_evaluator.engine.single_turn import build_turn_from_response
from skill_evaluator.engine.trace import Trace
from skill_evaluator.tools.matcher import match_tool_response

logger = logging.getLogger(__name__)


class MultiTurnExecutionError(Exception):
    """Raised when a multi-turn execution fails."""


class MultiTurnExecutor:
    """Executes an agentic loop: API call -> match tool calls -> inject responses -> repeat."""

    def __init__(
        self,
        client: Anthropic,
        defaults: SuiteDefaults,
        tools: list[dict[str, Any]] | None = None,
        tool_responses: list[ToolResponseConfig] | None = None,
        max_turns: int = 10,
    ) -> None:
        self.client = client
        self.defaults = defaults
        self.tools = tools
        self.tool_responses = tool_responses or []
        self.max_turns = max_turns

    def execute(self, system_prompt: str, input_config: InputConfig) -> Trace:
        """Run the agentic loop and return a Trace of all turns."""
        messages = build_messages(input_config.messages)
        trace = Trace()
        call_counts: dict[int, int] = {}

        logger.debug(
            "Multi-turn loop: model=%s, max_turns=%d, response_rules=%d",
            self.defaults.model, self.max_turns, len(self.tool_responses),
        )

        for turn_num in range(self.max_turns):
            kwargs: dict[str, Any] = {
                "model": self.defaults.model,
                "max_tokens": self.defaults.max_tokens,
                "system": system_prompt,
                "messages": messages,
            }
            if self.defaults.temperature is not None:
                kwargs["temperature"] = self.defaults.temperature
            if self.tools:
                kwargs["tools"] = self.tools

            try:
                response = self.client.messages.create(**kwargs)
            except Exception as e:
                logger.error("API call failed on turn %d: %s", turn_num, e)
                raise MultiTurnExecutionError(f"API call failed: {e}") from e

            turn = build_turn_from_response(response)
            trace.add_turn(turn)

            logger.debug(
                "Turn %d: stop_reason=%s, messages=%d, tool_calls=%d",
                turn_num, turn.stop_reason, len(messages), len(turn.tool_calls),
            )

            if turn.stop_reason != "tool_use":
                break

            # Build assistant message from raw response content
            assistant_content: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            messages.append({"role": "assistant", "content": assistant_content})

            # Match tool calls to scripted responses
            tool_result_blocks: list[dict[str, Any]] = []
            for tc in turn.tool_calls:
                matched = match_tool_response(tc, self.tool_responses, call_counts)
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": json.dumps(matched) if not isinstance(matched.get("content"), str) else matched["content"],
                })
            messages.append({"role": "user", "content": tool_result_blocks})

        logger.info("Multi-turn loop complete after %d turn(s)", len(trace.turns))
        return trace
