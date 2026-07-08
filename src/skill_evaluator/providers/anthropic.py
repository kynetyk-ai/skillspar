"""Anthropic provider — wraps the Anthropic SDK behind the Provider protocol."""

from __future__ import annotations

import logging
import os
from typing import Any

from anthropic import Anthropic, APIError

from skill_evaluator.engine.trace import TokenUsage, ToolCall, Turn
from skill_evaluator.providers.base import ProviderError

logger = logging.getLogger(__name__)


def build_turn_from_response(response: Any) -> Turn:
    """Extract text, tool calls, and usage from an Anthropic response into a Turn."""
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(
                ToolCall(
                    id=block.id,
                    name=block.name,
                    input=block.input,
                )
            )

    usage = TokenUsage(
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_creation_input_tokens=getattr(response.usage, "cache_creation_input_tokens", None),
        cache_read_input_tokens=getattr(response.usage, "cache_read_input_tokens", None),
    )

    return Turn(
        text_output="\n".join(text_parts),
        tool_calls=tool_calls,
        stop_reason=response.stop_reason,
        usage=usage,
        raw_response=response,
    )


class AnthropicProvider:
    """Provider adapter for the Anthropic Messages API.

    Passes the canonical message format through unchanged, including
    ``cache_control`` breakpoints. Anthropic stop reasons are already the
    canonical normalized values.
    """

    name = "anthropic"

    def __init__(
        self,
        client: Anthropic | None = None,
        *,
        max_retries: int = 2,
        api_key_env: str | None = None,
    ) -> None:
        if client is not None:
            self.client = client
        elif api_key_env:
            self.client = Anthropic(max_retries=max_retries, api_key=os.environ.get(api_key_env))
        else:
            self.client = Anthropic(max_retries=max_retries)

    def create_message(
        self,
        *,
        model: str,
        system: str | list[dict],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float | None,
    ) -> Turn:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = tools

        logger.debug(
            "Anthropic API call: model=%s, max_tokens=%d, temperature=%s, tools=%d, messages=%d",
            model,
            max_tokens,
            temperature,
            len(tools or []),
            len(messages),
        )

        try:
            response = self.client.messages.create(**kwargs)
        except APIError as e:
            raise ProviderError(f"API call failed: {e}") from e

        logger.debug(
            "Anthropic API response: stop_reason=%s, input_tokens=%d, output_tokens=%d",
            response.stop_reason,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return build_turn_from_response(response)
