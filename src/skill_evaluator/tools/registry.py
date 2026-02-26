"""Tool definition management."""

from __future__ import annotations

from skill_evaluator.config.schema import BuiltinToolConfig, CustomToolConfig, ToolConfig
from skill_evaluator.tools.builtins import get_builtin_tool


class ToolRegistryError(Exception):
    """Raised when tool resolution fails."""


def resolve_tools(tool_configs: list[ToolConfig] | None) -> list[dict]:
    """Convert tool configs into API-ready tool dicts.

    Returns an empty list for ``None`` or empty input.
    Raises ``ToolRegistryError`` for unknown built-in tool names.
    """
    if not tool_configs:
        return []

    tools: list[dict] = []
    for config in tool_configs:
        if isinstance(config, BuiltinToolConfig):
            try:
                tools.append(get_builtin_tool(config.builtin))
            except KeyError as e:
                raise ToolRegistryError(str(e)) from None
        elif isinstance(config, CustomToolConfig):
            tools.append(
                {
                    "name": config.name,
                    "description": config.description,
                    "input_schema": config.input_schema,
                }
            )
    return tools
