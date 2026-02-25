"""SingleTurnExecutor — one API call, assert on response."""

from __future__ import annotations

from typing import Any

from anthropic import Anthropic

from skill_evaluator.config.schema import InputConfig, SuiteDefaults
from skill_evaluator.engine.conversation import build_messages
from skill_evaluator.engine.trace import TokenUsage, ToolCall, Trace, Turn


class ExecutionError(Exception):
    """Raised when a single-turn execution fails."""


def build_turn_from_response(response: Any) -> Turn:
    """Extract text, tool calls, and usage from an API response into a Turn."""
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(ToolCall(
                id=block.id,
                name=block.name,
                input=block.input,
            ))

    usage = TokenUsage(
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_creation_input_tokens=getattr(
            response.usage, "cache_creation_input_tokens", None
        ),
        cache_read_input_tokens=getattr(
            response.usage, "cache_read_input_tokens", None
        ),
    )

    return Turn(
        text_output="\n".join(text_parts),
        tool_calls=tool_calls,
        stop_reason=response.stop_reason,
        usage=usage,
        raw_response=response,
    )


class SingleTurnExecutor:
    """Executes a single API call and returns a Trace."""

    def __init__(self, client: Anthropic, defaults: SuiteDefaults) -> None:
        self.client = client
        self.defaults = defaults

    def execute(
        self,
        system_prompt: str,
        input_config: InputConfig,
        tools: list[dict[str, Any]] | None = None,
    ) -> Trace:
        """Send messages to the API and return a Trace of the response."""
        messages = build_messages(input_config.messages)

        kwargs: dict[str, Any] = {
            "model": self.defaults.model,
            "max_tokens": self.defaults.max_tokens,
            "system": system_prompt,
            "messages": messages,
        }
        if self.defaults.temperature is not None:
            kwargs["temperature"] = self.defaults.temperature
        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.messages.create(**kwargs)
        except Exception as e:
            raise ExecutionError(f"API call failed: {e}") from e

        return self._build_trace(response)

    def _build_trace(self, response: Any) -> Trace:
        """Extract a single-turn Trace from an API response."""
        turn = build_turn_from_response(response)
        trace = Trace()
        trace.add_turn(turn)
        return trace
