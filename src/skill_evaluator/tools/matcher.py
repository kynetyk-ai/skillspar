"""Response matching for multi-turn mock tool responses."""

from __future__ import annotations

from skill_evaluator.config.schema import ToolMatchConfig, ToolResponseConfig
from skill_evaluator.engine.trace import ToolCall


class NoMatchError(Exception):
    """Raised when no tool response matches a tool call."""


def match_tool_response(
    tool_call: ToolCall,
    tool_responses: list[ToolResponseConfig],
) -> dict:
    """Find the first matching response for a tool call.

    Match rules (first match wins):
    - ``match: "*"`` — wildcard, matches any tool call
    - ``match: {tool: "Read"}`` — matches by tool name
    - ``match: {tool: null}`` — matches any tool call

    Raises ``NoMatchError`` if nothing matches.
    """
    for tr in tool_responses:
        if _matches(tr.match, tool_call):
            return tr.response
    raise NoMatchError(
        f"No matching tool response for tool call '{tool_call.name}' "
        f"(id={tool_call.id})"
    )


def _matches(match: ToolMatchConfig | str, tool_call: ToolCall) -> bool:
    if isinstance(match, str):
        return match == "*"
    # ToolMatchConfig
    if match.tool is None:
        return True
    return match.tool == tool_call.name
