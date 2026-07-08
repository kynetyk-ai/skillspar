"""Provider protocol — the API boundary between the engine and model vendors.

Executors and the LLM judge speak to a ``Provider`` instead of a vendor SDK.
Requests use the canonical Anthropic wire format that ``build_messages()``
emits (content blocks, ``tool_use``/``tool_result``, ``cache_control``);
adapters translate at the boundary. Responses are normalized into the
provider-neutral ``Turn``.

Normalized stop reasons: ``end_turn``, ``tool_use``, ``max_tokens``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from skill_evaluator.engine.trace import Turn


class ProviderError(Exception):
    """Raised when a provider API call fails or a provider cannot be built."""


@runtime_checkable
class Provider(Protocol):
    """A model API adapter."""

    name: str

    def create_message(
        self,
        *,
        model: str,
        system: str | list[dict],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float | None,
    ) -> Turn: ...
