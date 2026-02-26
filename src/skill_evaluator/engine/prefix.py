"""Prefix loader for mid-conversation testing."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from skill_evaluator.config.schema import ConversationPrefixConfig, MessageConfig

logger = logging.getLogger(__name__)

# Anthropic API minimum for prompt caching — prefixes shorter than this
# token count will not be cached, even with cache_control markers set.
MINIMUM_CACHE_TOKEN_THRESHOLD = 1024


class PrefixLoadError(Exception):
    """Raised when conversation prefix messages cannot be loaded."""


def load_prefix_messages(
    eval_file: Path,
    prefix_config: ConversationPrefixConfig,
    *,
    enable_caching: bool = True,
) -> list[MessageConfig]:
    """Load and validate prefix messages from inline config or external file.

    Returns a list of MessageConfig objects. If enable_caching is True, sets
    cache_control={"type": "ephemeral"} on the last message.
    """
    if prefix_config.messages is not None:
        messages = list(prefix_config.messages)
    else:
        assert prefix_config.file is not None
        messages = _load_external_prefix(eval_file, prefix_config.file)

    _validate_prefix_messages(messages)

    if enable_caching and messages:
        # Tag the last message for cache breakpoint
        last = messages[-1]
        messages[-1] = MessageConfig(
            role=last.role,
            content=last.content,
            tool_calls=last.tool_calls,
            tool_use_id=last.tool_use_id,
            cache_control={"type": "ephemeral"},
        )

    return messages


def _load_external_prefix(eval_file: Path, file_ref: str) -> list[MessageConfig]:
    """Load prefix messages from an external YAML file."""
    path = (eval_file.parent / file_ref).resolve()
    if not path.exists():
        raise PrefixLoadError(f"Prefix file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise PrefixLoadError(f"Invalid YAML in prefix file {path}: {e}") from e

    if not isinstance(raw, list):
        raise PrefixLoadError(
            f"Prefix file must contain a YAML list of messages, got {type(raw).__name__}"
        )

    try:
        return [MessageConfig.model_validate(item) for item in raw]
    except ValidationError as e:
        raise PrefixLoadError(f"Invalid message in prefix file {path}: {e}") from e


def _validate_prefix_messages(messages: list[MessageConfig]) -> None:
    """Validate that prefix messages are non-empty and end with assistant."""
    if not messages:
        raise PrefixLoadError("Prefix messages must not be empty")
    if messages[-1].role != "assistant":
        raise PrefixLoadError("Prefix messages must end with an assistant message")


def estimate_prefix_tokens(messages: list[MessageConfig]) -> int:
    """Rough estimate of token count using ~4 chars per token heuristic."""
    total_chars = sum(len(m.content or "") for m in messages)
    return total_chars // 4
