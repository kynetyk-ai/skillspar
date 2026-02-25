"""Message builder utilities for converting YAML messages to API format."""

from __future__ import annotations

from skill_evaluator.config.schema import MessageConfig


class ConversationBuildError(Exception):
    """Raised when messages cannot be converted to API format."""


def build_skill_messages(
    skill_body: str, *, cache_control: dict[str, str] | None = None
) -> list[MessageConfig]:
    """Build a user message containing the skill body with contextual framing."""
    framed = (
        "The following skill has been activated for this task:\n\n"
        f"{skill_body}"
    )
    return [MessageConfig(role="user", content=framed, cache_control=cache_control)]


def build_messages(messages: list[MessageConfig]) -> list[dict]:
    """Convert YAML message configs to Anthropic API message format.

    Handles:
    - User messages: passed through as-is
    - Assistant messages with tool_calls: converted to content blocks
    - tool_result messages: wrapped in user messages with tool_result blocks;
      consecutive tool_results are merged into a single user message
    """
    api_messages: list[dict] = []

    for msg in messages:
        if msg.role == "user":
            if msg.cache_control:
                api_messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": msg.content or "", "cache_control": msg.cache_control}
                    ],
                })
            else:
                api_messages.append({"role": "user", "content": msg.content or ""})

        elif msg.role == "assistant":
            content: list[dict] = []
            if msg.content:
                text_block: dict = {"type": "text", "text": msg.content}
                content.append(text_block)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.input,
                    })
            # Add cache_control to the last content block for assistant messages
            if msg.cache_control and content:
                content[-1]["cache_control"] = msg.cache_control
            api_messages.append({
                "role": "assistant",
                "content": content if content else (msg.content or ""),
            })

        elif msg.role == "tool_result":
            tool_result_block = {
                "type": "tool_result",
                "tool_use_id": msg.tool_use_id,
                "content": msg.content or "",
            }
            # Merge consecutive tool_results into one user message
            if api_messages and api_messages[-1]["role"] == "user":
                last = api_messages[-1]
                if isinstance(last["content"], list):
                    last["content"].append(tool_result_block)
                else:
                    # Previous user message had plain text — shouldn't happen
                    # for tool_result merging, but handle gracefully
                    api_messages.append({
                        "role": "user",
                        "content": [tool_result_block],
                    })
            else:
                api_messages.append({
                    "role": "user",
                    "content": [tool_result_block],
                })

        else:
            raise ConversationBuildError(f"Unknown message role: {msg.role}")

    return _coalesce_consecutive_roles(api_messages)


def _coalesce_consecutive_roles(api_messages: list[dict]) -> list[dict]:
    """Merge consecutive messages that share the same role.

    String content is normalised to ``[{"type": "text", "text": ...}]``
    list format before merging so that all content blocks can be concatenated.
    """
    if not api_messages:
        return api_messages

    def _to_list(content: str | list) -> list[dict]:
        if isinstance(content, str):
            return [{"type": "text", "text": content}]
        return list(content)

    merged: list[dict] = [api_messages[0]]
    for msg in api_messages[1:]:
        if msg["role"] == merged[-1]["role"]:
            merged[-1]["content"] = _to_list(merged[-1]["content"]) + _to_list(msg["content"])
        else:
            merged.append(msg)
    return merged
