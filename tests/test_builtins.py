"""Tests for tools/builtins.py — built-in tool schemas."""

import pytest

from skill_evaluator.tools.builtins import get_builtin_tool, _BUILTINS


EXPECTED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]


class TestBuiltinTools:
    @pytest.mark.parametrize("name", EXPECTED_TOOLS)
    def test_tool_has_required_keys(self, name):
        tool = get_builtin_tool(name)
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert tool["name"] == name

    @pytest.mark.parametrize("name", EXPECTED_TOOLS)
    def test_input_schema_is_object_type(self, name):
        tool = get_builtin_tool(name)
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

    def test_get_builtin_tool_works(self):
        tool = get_builtin_tool("Read")
        assert tool["name"] == "Read"

    def test_unknown_name_raises(self):
        with pytest.raises(KeyError, match="Unknown built-in tool"):
            get_builtin_tool("NotATool")

    def test_all_expected_tools_present(self):
        for name in EXPECTED_TOOLS:
            assert name in _BUILTINS
