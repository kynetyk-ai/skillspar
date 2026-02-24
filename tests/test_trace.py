"""Tests for engine/trace.py — Trace property aggregation."""

from skill_evaluator.engine.trace import ToolCall, Trace, Turn


class TestTrace:
    def test_empty_trace(self):
        trace = Trace()
        assert trace.text_output == ""
        assert trace.tool_calls == []
        assert trace.tool_names == []
        assert trace.stop_reason is None
        assert trace.turn_count == 0

    def test_single_turn_text(self, simple_text_trace):
        assert "Hello Alice" in simple_text_trace.text_output
        assert simple_text_trace.stop_reason == "end_turn"
        assert simple_text_trace.turn_count == 1

    def test_tool_calls(self, tool_call_trace):
        assert len(tool_call_trace.tool_calls) == 1
        assert tool_call_trace.tool_names == ["Write"]
        assert tool_call_trace.stop_reason == "tool_use"

    def test_multi_turn_aggregation(self, sample_usage):
        trace = Trace()
        trace.add_turn(Turn(
            text_output="First",
            tool_calls=[ToolCall(id="tc_1", name="Read", input={})],
            stop_reason="tool_use",
            usage=sample_usage,
            raw_response=None,
        ))
        trace.add_turn(Turn(
            text_output="Second",
            tool_calls=[ToolCall(id="tc_2", name="Write", input={})],
            stop_reason="end_turn",
            usage=sample_usage,
            raw_response=None,
        ))

        assert trace.text_output == "First\nSecond"
        assert trace.tool_names == ["Read", "Write"]
        assert trace.stop_reason == "end_turn"
        assert trace.turn_count == 2

    def test_total_usage(self, sample_usage):
        trace = Trace()
        trace.add_turn(Turn(
            text_output="a", tool_calls=[], stop_reason="end_turn",
            usage=sample_usage, raw_response=None,
        ))
        trace.add_turn(Turn(
            text_output="b", tool_calls=[], stop_reason="end_turn",
            usage=sample_usage, raw_response=None,
        ))
        total = trace.total_usage
        assert total.input_tokens == 200
        assert total.output_tokens == 100
