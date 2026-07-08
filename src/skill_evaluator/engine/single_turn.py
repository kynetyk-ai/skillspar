"""SingleTurnExecutor — one API call, assert on response."""

from __future__ import annotations

import logging
from typing import Any

from skill_evaluator.config.schema import InputConfig, ResolvedConfig
from skill_evaluator.engine.conversation import build_messages
from skill_evaluator.engine.trace import Trace, Turn
from skill_evaluator.providers.anthropic import build_turn_from_response
from skill_evaluator.providers.base import Provider, ProviderError

__all__ = ["ExecutionError", "SingleTurnExecutor", "build_turn_from_response"]

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    """Raised when a single-turn execution fails."""


class SingleTurnExecutor:
    """Executes a single API call and returns a Trace."""

    def __init__(self, provider: Provider, config: ResolvedConfig) -> None:
        self.provider = provider
        self.config = config

    def execute(
        self,
        system_prompt: str | list[dict],
        input_config: InputConfig,
        tools: list[dict[str, Any]] | None = None,
    ) -> Trace:
        """Send messages to the API and return a Trace of the response."""
        messages = build_messages(input_config.messages)

        try:
            turn = self.provider.create_message(
                model=self.config.model,
                system=system_prompt,
                messages=messages,
                tools=tools or None,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
        except ProviderError as e:
            logger.error("API call failed: %s", e)
            raise ExecutionError(str(e)) from e

        return self._build_trace(turn)

    def _build_trace(self, turn: Turn) -> Trace:
        """Wrap a single turn in a Trace."""
        trace = Trace()
        trace.add_turn(turn)
        return trace
