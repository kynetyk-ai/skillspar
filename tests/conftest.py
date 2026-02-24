"""Shared fixtures for the test suite."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from skill_evaluator.engine.trace import TokenUsage, ToolCall, Trace, Turn


@pytest.fixture
def sample_usage():
    return TokenUsage(input_tokens=100, output_tokens=50)


@pytest.fixture
def simple_text_trace(sample_usage):
    trace = Trace()
    trace.add_turn(Turn(
        text_output="Hello Alice! How can I help you today?",
        tool_calls=[],
        stop_reason="end_turn",
        usage=sample_usage,
        raw_response=None,
    ))
    return trace


@pytest.fixture
def tool_call_trace(sample_usage):
    trace = Trace()
    trace.add_turn(Turn(
        text_output="I'll create that file for you.",
        tool_calls=[
            ToolCall(id="tc_001", name="Write", input={"file_path": "/hello.txt", "content": "hi"}),
        ],
        stop_reason="tool_use",
        usage=sample_usage,
        raw_response=None,
    ))
    return trace


@pytest.fixture
def mock_anthropic_message(sample_usage):
    """Create a mock Anthropic Message response."""
    def _make(text="Hello!", tool_uses=None, stop_reason="end_turn"):
        msg = MagicMock()
        msg.stop_reason = stop_reason

        content = []
        if text:
            text_block = MagicMock()
            text_block.type = "text"
            text_block.text = text
            content.append(text_block)
        if tool_uses:
            for tu in tool_uses:
                block = MagicMock()
                block.type = "tool_use"
                block.id = tu["id"]
                block.name = tu["name"]
                block.input = tu["input"]
                content.append(block)
        msg.content = content

        msg.usage = MagicMock()
        msg.usage.input_tokens = sample_usage.input_tokens
        msg.usage.output_tokens = sample_usage.output_tokens
        msg.usage.cache_creation_input_tokens = None
        msg.usage.cache_read_input_tokens = None
        return msg
    return _make


@pytest.fixture
def mock_anthropic_client(mock_anthropic_message):
    """Create a mock Anthropic client with a pre-configured response."""
    client = MagicMock()
    client.messages.create.return_value = mock_anthropic_message()
    return client
