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

    def test_sequence_returns_in_order(self):
        responses = [
            ToolResponseConfig(
                match=ToolMatchConfig(tool="Read"),
                responses=[{"content": "first"}, {"content": "second"}, {"content": "third"}],
            ),
        ]
        counts: dict[int, int] = {}
        assert match_tool_response(_tc("Read"), responses, counts) == {"content": "first"}
        assert match_tool_response(_tc("Read"), responses, counts) == {"content": "second"}
        assert match_tool_response(_tc("Read"), responses, counts) == {"content": "third"}

    def test_sequence_clamps_to_last(self):
        responses = [
            ToolResponseConfig(
                match=ToolMatchConfig(tool="Read"),
                responses=[{"content": "one"}, {"content": "two"}],
            ),
        ]
        counts: dict[int, int] = {}
        match_tool_response(_tc("Read"), responses, counts)
        match_tool_response(_tc("Read"), responses, counts)
        assert match_tool_response(_tc("Read"), responses, counts) == {"content": "two"}
        assert match_tool_response(_tc("Read"), responses, counts) == {"content": "two"}

    def test_independent_counters_per_rule(self):
        responses = [
            ToolResponseConfig(
                match=ToolMatchConfig(tool="Read"),
                responses=[{"content": "r1"}, {"content": "r2"}],
            ),
            ToolResponseConfig(
                match=ToolMatchConfig(tool="Write"),
                responses=[{"content": "w1"}, {"content": "w2"}],
            ),
        ]
        counts: dict[int, int] = {}
        assert match_tool_response(_tc("Read"), responses, counts) == {"content": "r1"}
        assert match_tool_response(_tc("Write"), responses, counts) == {"content": "w1"}
        assert match_tool_response(_tc("Read"), responses, counts) == {"content": "r2"}
        assert match_tool_response(_tc("Write"), responses, counts) == {"content": "w2"}

    def test_single_response_with_call_counts(self):
        responses = [
            ToolResponseConfig(match="*", response={"content": "static"}),
        ]
        counts: dict[int, int] = {}
        assert match_tool_response(_tc("Read"), responses, counts) == {"content": "static"}
        assert match_tool_response(_tc("Read"), responses, counts) == {"content": "static"}
        assert counts[0] == 2

    def test_no_call_counts_backward_compat(self):
        responses = [
            ToolResponseConfig(match="*", response={"content": "ok"}),
        ]
        assert match_tool_response(_tc("Read"), responses) == {"content": "ok"}
        assert match_tool_response(_tc("Read"), responses) == {"content": "ok"}
