"""Trace, Turn, and ToolCall data models for capturing execution results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "input": self.input}


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }
        if self.cache_creation_input_tokens is not None:
            d["cache_creation_input_tokens"] = self.cache_creation_input_tokens
        if self.cache_read_input_tokens is not None:
            d["cache_read_input_tokens"] = self.cache_read_input_tokens
        return d


@dataclass(frozen=True)
class Turn:
    text_output: str
    tool_calls: list[ToolCall]
    stop_reason: str
    usage: TokenUsage
    raw_response: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "text_output": self.text_output,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "stop_reason": self.stop_reason,
            "usage": self.usage.to_dict(),
        }


@dataclass
class Trace:
    turns: list[Turn] = field(default_factory=list)

    def add_turn(self, turn: Turn) -> None:
        self.turns.append(turn)

    @property
    def text_output(self) -> str:
        return "\n".join(t.text_output for t in self.turns if t.text_output)

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [tc for t in self.turns for tc in t.tool_calls]

    @property
    def tool_names(self) -> list[str]:
        return [tc.name for tc in self.tool_calls]

    @property
    def stop_reason(self) -> str | None:
        if not self.turns:
            return None
        return self.turns[-1].stop_reason

    @property
    def total_usage(self) -> TokenUsage:
        input_tokens = sum(t.usage.input_tokens for t in self.turns)
        output_tokens = sum(t.usage.output_tokens for t in self.turns)

        # Sum cache tokens; return None when all turns have None
        cache_creation_values = [
            t.usage.cache_creation_input_tokens
            for t in self.turns
            if t.usage.cache_creation_input_tokens is not None
        ]
        cache_creation = sum(cache_creation_values) if cache_creation_values else None

        cache_read_values = [
            t.usage.cache_read_input_tokens
            for t in self.turns
            if t.usage.cache_read_input_tokens is not None
        ]
        cache_read = sum(cache_read_values) if cache_read_values else None

        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
        )

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def to_dict(self) -> dict[str, Any]:
        return {"turns": [t.to_dict() for t in self.turns]}
