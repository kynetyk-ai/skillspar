"""Tests for tools/matcher.py — tool response matching."""

import pytest

from skill_evaluator.config.schema import ToolMatchConfig, ToolResponseConfig
from skill_evaluator.engine.trace import ToolCall
from skill_evaluator.tools.matcher import NoMatchError, match_tool_response


def _tc(name: str, tool_id: str = "tc_001") -> ToolCall:
    return ToolCall(id=tool_id, name=name, input={})


class TestMatchToolResponse:
    def test_wildcard_matches_anything(self):
        responses = [
            ToolResponseConfig(match="*", response={"content": "OK"}),
        ]
        result = match_tool_response(_tc("Read"), responses)
        assert result == {"content": "OK"}

    def test_name_match(self):
        responses = [
            ToolResponseConfig(
                match=ToolMatchConfig(tool="Read"),
                response={"content": "file contents"},
            ),
            ToolResponseConfig(
                match=ToolMatchConfig(tool="Write"),
                response={"content": "written"},
            ),
        ]
        result = match_tool_response(_tc("Write"), responses)
        assert result == {"content": "written"}

    def test_first_match_wins(self):
        responses = [
            ToolResponseConfig(
                match=ToolMatchConfig(tool="Read"),
                response={"content": "first"},
            ),
            ToolResponseConfig(
                match=ToolMatchConfig(tool="Read"),
                response={"content": "second"},
            ),
        ]
        result = match_tool_response(_tc("Read"), responses)
        assert result == {"content": "first"}

    def test_no_match_raises(self):
        responses = [
            ToolResponseConfig(
                match=ToolMatchConfig(tool="Write"),
                response={"content": "written"},
            ),
        ]
        with pytest.raises(NoMatchError, match="Read"):
            match_tool_response(_tc("Read"), responses)

    def test_null_tool_matches_all(self):
        responses = [
            ToolResponseConfig(
                match=ToolMatchConfig(tool=None),
                response={"content": "catch-all"},
            ),
        ]
        result = match_tool_response(_tc("Bash"), responses)
        assert result == {"content": "catch-all"}

    def test_specific_before_wildcard(self):
        responses = [
            ToolResponseConfig(
                match=ToolMatchConfig(tool="Read"),
                response={"content": "specific"},
            ),
            ToolResponseConfig(match="*", response={"content": "wildcard"}),
        ]
        assert match_tool_response(_tc("Read"), responses) == {"content": "specific"}
        assert match_tool_response(_tc("Write"), responses) == {"content": "wildcard"}
