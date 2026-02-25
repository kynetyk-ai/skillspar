"""Tests for engine/trace.py — Trace property aggregation."""

from skill_evaluator.engine.trace import TokenUsage, ToolCall, Trace, Turn


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


class TestTokenUsageToDict:
    def test_basic_fields_only(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        d = usage.to_dict()
        assert d == {"input_tokens": 100, "output_tokens": 50}
        assert "cache_creation_input_tokens" not in d
        assert "cache_read_input_tokens" not in d

    def test_with_cache_creation(self):
        usage = TokenUsage(
            input_tokens=100, output_tokens=50,
            cache_creation_input_tokens=200,
        )
        d = usage.to_dict()
        assert d["cache_creation_input_tokens"] == 200
        assert "cache_read_input_tokens" not in d

    def test_with_cache_read(self):
        usage = TokenUsage(
            input_tokens=100, output_tokens=50,
            cache_read_input_tokens=300,
        )
        d = usage.to_dict()
        assert d["cache_read_input_tokens"] == 300
        assert "cache_creation_input_tokens" not in d

    def test_with_both_cache_fields(self):
        usage = TokenUsage(
            input_tokens=100, output_tokens=50,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=300,
        )
        d = usage.to_dict()
        assert d == {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 200,
            "cache_read_input_tokens": 300,
        }


class TestTraceCacheTokenAggregation:
    def test_no_cache_tokens_returns_none(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        trace = Trace()
        trace.add_turn(Turn(
            text_output="a", tool_calls=[], stop_reason="end_turn",
            usage=usage, raw_response=None,
        ))
        trace.add_turn(Turn(
            text_output="b", tool_calls=[], stop_reason="end_turn",
            usage=usage, raw_response=None,
        ))
        total = trace.total_usage
        assert total.cache_creation_input_tokens is None
        assert total.cache_read_input_tokens is None

    def test_cache_tokens_summed(self):
        usage1 = TokenUsage(
            input_tokens=100, output_tokens=50,
            cache_creation_input_tokens=200, cache_read_input_tokens=0,
        )
        usage2 = TokenUsage(
            input_tokens=100, output_tokens=50,
            cache_creation_input_tokens=0, cache_read_input_tokens=400,
        )
        trace = Trace()
        trace.add_turn(Turn(
            text_output="a", tool_calls=[], stop_reason="end_turn",
            usage=usage1, raw_response=None,
        ))
        trace.add_turn(Turn(
            text_output="b", tool_calls=[], stop_reason="end_turn",
            usage=usage2, raw_response=None,
        ))
        total = trace.total_usage
        assert total.cache_creation_input_tokens == 200
        assert total.cache_read_input_tokens == 400

    def test_mixed_none_and_values(self):
        """When some turns have cache tokens and some don't, sum the non-None values."""
        usage_with = TokenUsage(
            input_tokens=100, output_tokens=50,
            cache_creation_input_tokens=150,
        )
        usage_without = TokenUsage(input_tokens=100, output_tokens=50)
        trace = Trace()
        trace.add_turn(Turn(
            text_output="a", tool_calls=[], stop_reason="end_turn",
            usage=usage_with, raw_response=None,
        ))
        trace.add_turn(Turn(
            text_output="b", tool_calls=[], stop_reason="end_turn",
            usage=usage_without, raw_response=None,
        ))
        total = trace.total_usage
        assert total.cache_creation_input_tokens == 150
        assert total.cache_read_input_tokens is None
