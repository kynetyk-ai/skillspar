"""OpenAI-compatible provider — Chat Completions adapter for the Provider protocol.

Covers any endpoint speaking the OpenAI Chat Completions API: OpenAI itself,
OpenRouter, LiteLLM, Ollama, vLLM, and others via ``base_url``.

Translation happens at this boundary in both directions:

- Requests arrive in the canonical Anthropic wire format (content blocks,
  ``tool_use``/``tool_result``, top-level ``system``) and are converted to
  Chat Completions messages/tools. ``cache_control`` markers are stripped —
  OpenAI-compatible endpoints cache automatically, with no explicit
  breakpoints.
- Responses are normalized into the provider-neutral ``Turn``, mapping
  ``finish_reason`` to the canonical stop reasons.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from skill_evaluator.engine.trace import TokenUsage, ToolCall, Turn
from skill_evaluator.providers.base import ProviderError

logger = logging.getLogger(__name__)

_FINISH_REASON_MAP = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "length": "max_tokens",
}


def _flatten_text_blocks(content: str | list[dict]) -> str:
    """Flatten a string or list of Anthropic text blocks into a plain string."""
    if isinstance(content, str):
        return content
    return "\n".join(block.get("text", "") for block in content if block.get("type") == "text")


def _to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic tool schemas to OpenAI function-tool schemas."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool["input_schema"],
            },
        }
        for tool in tools
    ]


def _to_openai_messages(
    system: str | list[dict], messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Convert canonical Anthropic-format messages to Chat Completions messages."""
    result: list[dict[str, Any]] = []

    system_text = _flatten_text_blocks(system)
    if system_text:
        result.append({"role": "system", "content": system_text})

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            result.append({"role": role, "content": content})
            continue

        if role == "user":
            # tool_result blocks become standalone role:"tool" messages;
            # remaining text blocks are concatenated into a user message.
            text_parts: list[str] = []
            for block in content:
                if block.get("type") == "tool_result":
                    tool_content = block.get("content", "")
                    if not isinstance(tool_content, str):
                        tool_content = _flatten_text_blocks(tool_content)
                    result.append(
                        {
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": tool_content,
                        }
                    )
                elif block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            if text_parts:
                result.append({"role": "user", "content": "\n".join(text_parts)})

        elif role == "assistant":
            text_parts = []
            tool_calls: list[dict[str, Any]] = []
            for block in content:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_calls.append(
                        {
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        }
                    )
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": "\n".join(text_parts) if text_parts else None,
            }
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            result.append(assistant_msg)

        else:
            result.append({"role": role, "content": _flatten_text_blocks(content)})

    return result


def _turn_from_completion(response: Any) -> Turn:
    """Normalize a Chat Completions response into a Turn."""
    choice = response.choices[0]
    message = choice.message

    tool_calls: list[ToolCall] = []
    for tc in message.tool_calls or []:
        try:
            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
        except json.JSONDecodeError:
            logger.warning(
                "Tool call '%s' returned malformed argument JSON; treating as empty input",
                tc.function.name,
            )
            args = {}
        tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=args))

    cached_tokens = None
    usage = response.usage
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached_tokens = getattr(details, "cached_tokens", None)

    finish_reason = choice.finish_reason or "end_turn"
    return Turn(
        text_output=message.content or "",
        tool_calls=tool_calls,
        stop_reason=_FINISH_REASON_MAP.get(finish_reason, finish_reason),
        usage=TokenUsage(
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cache_creation_input_tokens=None,
            cache_read_input_tokens=cached_tokens,
        ),
        raw_response=response,
    )


class OpenAICompatProvider:
    """Provider adapter for OpenAI-compatible Chat Completions endpoints."""

    name = "openai"

    def __init__(
        self,
        client: Any | None = None,
        *,
        base_url: str | None = None,
        api_key_env: str | None = None,
        max_retries: int = 2,
    ) -> None:
        if client is not None:
            self.client = client
            return
        try:
            from openai import OpenAI  # pyright: ignore[reportMissingImports]
        except ImportError as e:
            raise ProviderError(
                "The openai provider requires the openai SDK. "
                "Install it with: pip install 'skillspar[openai]'"
            ) from e
        self.client = OpenAI(
            base_url=base_url,
            api_key=os.environ.get(api_key_env or "OPENAI_API_KEY"),
            max_retries=max_retries,
        )

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
            "messages": _to_openai_messages(system, messages),
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = _to_openai_tools(tools)

        logger.debug(
            "OpenAI-compatible API call: model=%s, max_tokens=%d, temperature=%s, "
            "tools=%d, messages=%d",
            model,
            max_tokens,
            temperature,
            len(tools or []),
            len(kwargs["messages"]),
        )

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:  # openai SDK errors; SDK may not be importable here
            raise ProviderError(f"API call failed: {e}") from e

        turn = _turn_from_completion(response)
        logger.debug(
            "OpenAI-compatible API response: stop_reason=%s, input_tokens=%d, output_tokens=%d",
            turn.stop_reason,
            turn.usage.input_tokens,
            turn.usage.output_tokens,
        )
        return turn
