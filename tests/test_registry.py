"""Tests for tools/registry.py — tool resolution."""

import pytest

from skill_evaluator.config.schema import BuiltinToolConfig, CustomToolConfig
from skill_evaluator.tools.registry import ToolRegistryError, resolve_tools


class TestResolveTools:
    def test_none_returns_empty(self):
        assert resolve_tools(None) == []

    def test_empty_list_returns_empty(self):
        assert resolve_tools([]) == []

    def test_builtin_resolution(self):
        configs = [BuiltinToolConfig(builtin="Read")]
        tools = resolve_tools(configs)
        assert len(tools) == 1
        assert tools[0]["name"] == "Read"
        assert "input_schema" in tools[0]

    def test_custom_tool_passthrough(self):
        custom = CustomToolConfig(
            name="MyTool",
            description="A custom tool",
            input_schema={"type": "object", "properties": {}, "required": []},
        )
        tools = resolve_tools([custom])
        assert len(tools) == 1
        assert tools[0]["name"] == "MyTool"
        assert tools[0]["description"] == "A custom tool"

    def test_mixed_list(self):
        configs = [
            BuiltinToolConfig(builtin="Write"),
            CustomToolConfig(
                name="Custom",
                description="desc",
                input_schema={"type": "object", "properties": {}, "required": []},
            ),
        ]
        tools = resolve_tools(configs)
        assert len(tools) == 2
        assert tools[0]["name"] == "Write"
        assert tools[1]["name"] == "Custom"

    def test_unknown_builtin_raises(self):
        configs = [BuiltinToolConfig(builtin="UnknownTool")]
        with pytest.raises(ToolRegistryError, match="Unknown built-in tool"):
            resolve_tools(configs)
