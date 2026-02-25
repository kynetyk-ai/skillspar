"""Tests for engine/multi_turn.py — MultiTurnExecutor."""

import pytest

from skill_evaluator.config.schema import (
    InputConfig,
    MessageConfig,
    ResolvedConfig,
    ToolMatchConfig,
    ToolResponseConfig,
)
from skill_evaluator.engine.multi_turn import MultiTurnExecutionError, MultiTurnExecutor
from skill_evaluator.tools.matcher import NoMatchError


def _input(text: str = "Do something") -> InputConfig:
    return InputConfig(messages=[MessageConfig(role="user", content=text)])


def _config() -> ResolvedConfig:
    return ResolvedConfig(model="test-model", max_tokens=1024, temperature=0)


class TestMultiTurnExecutor:
    def test_single_turn_completion(self, mock_anthropic_client, mock_anthropic_message):
        """Model returns end_turn immediately — single turn, no tool loop."""
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Done!", stop_reason="end_turn"
        )
        executor = MultiTurnExecutor(
            client=mock_anthropic_client,
            config=_config(),
        )
        trace = executor.execute("You are helpful.", _input())
        assert trace.turn_count == 1
        assert trace.stop_reason == "end_turn"
        assert trace.text_output == "Done!"
        mock_anthropic_client.messages.create.assert_called_once()

    def test_two_turn_loop(self, mock_anthropic_client, mock_anthropic_message):
        """Model calls a tool, gets response, then finishes."""
        tool_response = mock_anthropic_message(
            text="Let me read that.",
            tool_uses=[{"id": "tc_001", "name": "Read", "input": {"file_path": "/f.txt"}}],
            stop_reason="tool_use",
        )
        final_response = mock_anthropic_message(
            text="Here's the content.", stop_reason="end_turn"
        )
        mock_anthropic_client.messages.create.side_effect = [tool_response, final_response]

        tool_responses = [
            ToolResponseConfig(match="*", response={"content": "file content"}),
        ]
        executor = MultiTurnExecutor(
            client=mock_anthropic_client,
            config=_config(),
            tool_responses=tool_responses,
        )
        trace = executor.execute("You are helpful.", _input())

        assert trace.turn_count == 2
        assert trace.stop_reason == "end_turn"
        assert "Read" in trace.tool_names
        assert mock_anthropic_client.messages.create.call_count == 2

    def test_max_turns_cap(self, mock_anthropic_client, mock_anthropic_message):
        """Loop stops at max_turns even if model keeps calling tools."""
        tool_msg = mock_anthropic_message(
            text="Calling tool.",
            tool_uses=[{"id": "tc_001", "name": "Read", "input": {"file_path": "/f.txt"}}],
            stop_reason="tool_use",
        )
        mock_anthropic_client.messages.create.return_value = tool_msg

        tool_responses = [
            ToolResponseConfig(match="*", response={"content": "ok"}),
        ]
        executor = MultiTurnExecutor(
            client=mock_anthropic_client,
            config=_config(),
            tool_responses=tool_responses,
            max_turns=3,
        )
        trace = executor.execute("You are helpful.", _input())

        assert trace.turn_count == 3
        assert trace.stop_reason == "tool_use"  # never got end_turn
        assert mock_anthropic_client.messages.create.call_count == 3

    def test_no_match_error(self, mock_anthropic_client, mock_anthropic_message):
        """NoMatchError propagates when no tool response matches."""
        tool_msg = mock_anthropic_message(
            text="Calling Bash.",
            tool_uses=[{"id": "tc_001", "name": "Bash", "input": {"command": "ls"}}],
            stop_reason="tool_use",
        )
        mock_anthropic_client.messages.create.return_value = tool_msg

        # Only match Read, not Bash
        tool_responses = [
            ToolResponseConfig(
                match=ToolMatchConfig(tool="Read"),
                response={"content": "data"},
            ),
        ]
        executor = MultiTurnExecutor(
            client=mock_anthropic_client,
            config=_config(),
            tool_responses=tool_responses,
        )
        with pytest.raises(NoMatchError, match="Bash"):
            executor.execute("You are helpful.", _input())

    def test_wildcard_catch_all(self, mock_anthropic_client, mock_anthropic_message):
        """Wildcard response matches any tool."""
        tool_msg = mock_anthropic_message(
            text="Running something.",
            tool_uses=[{"id": "tc_001", "name": "Glob", "input": {"pattern": "*.py"}}],
            stop_reason="tool_use",
        )
        final_msg = mock_anthropic_message(text="Found files.", stop_reason="end_turn")
        mock_anthropic_client.messages.create.side_effect = [tool_msg, final_msg]

        tool_responses = [
            ToolResponseConfig(match="*", response={"content": "matched"}),
        ]
        executor = MultiTurnExecutor(
            client=mock_anthropic_client,
            config=_config(),
            tool_responses=tool_responses,
        )
        trace = executor.execute("You are helpful.", _input())
        assert trace.turn_count == 2
        assert "Glob" in trace.tool_names

    def test_api_error_raises(self, mock_anthropic_client):
        """API errors are wrapped in MultiTurnExecutionError."""
        mock_anthropic_client.messages.create.side_effect = Exception("timeout")

        executor = MultiTurnExecutor(
            client=mock_anthropic_client,
            config=_config(),
        )
        with pytest.raises(MultiTurnExecutionError, match="timeout"):
            executor.execute("You are helpful.", _input())

    def test_tools_passed_to_api(self, mock_anthropic_client, mock_anthropic_message):
        """Tool schemas are forwarded to the API call."""
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Done", stop_reason="end_turn"
        )
        tools = [{"name": "Read", "description": "Read a file", "input_schema": {}}]
        executor = MultiTurnExecutor(
            client=mock_anthropic_client,
            config=_config(),
            tools=tools,
        )
        executor.execute("prompt", _input())

        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["tools"] == tools

    def test_messages_accumulate(self, mock_anthropic_client, mock_anthropic_message):
        """Messages grow with each turn (assistant + tool_result appended)."""
        tool_msg = mock_anthropic_message(
            text="Reading.",
            tool_uses=[{"id": "tc_001", "name": "Read", "input": {"file_path": "/a"}}],
            stop_reason="tool_use",
        )
        final_msg = mock_anthropic_message(text="Done.", stop_reason="end_turn")
        mock_anthropic_client.messages.create.side_effect = [tool_msg, final_msg]

        tool_responses = [
            ToolResponseConfig(match="*", response={"content": "data"}),
        ]
        executor = MultiTurnExecutor(
            client=mock_anthropic_client,
            config=_config(),
            tool_responses=tool_responses,
        )
        executor.execute("prompt", _input())

        # Second call should have 3 messages: user + assistant + user(tool_result)
        calls = mock_anthropic_client.messages.create.call_args_list
        assert len(calls) == 2
        # The messages list is mutated in place, so check that by the end
        # it contains the original user msg + assistant + tool_result
        final_msgs = calls[1].kwargs["messages"]
        assert len(final_msgs) == 3
        assert final_msgs[0]["role"] == "user"
        assert final_msgs[1]["role"] == "assistant"
        assert final_msgs[2]["role"] == "user"
        # The tool_result user message should contain tool_result blocks
        assert final_msgs[2]["content"][0]["type"] == "tool_result"

    def test_response_sequence(self, mock_anthropic_client, mock_anthropic_message):
        """Model calls Read 3 times, gets 3 different responses, then finishes."""
        read_msg_1 = mock_anthropic_message(
            text="Reading file.",
            tool_uses=[{"id": "tc_001", "name": "Read", "input": {"file_path": "/f"}}],
            stop_reason="tool_use",
        )
        read_msg_2 = mock_anthropic_message(
            text="Reading again.",
            tool_uses=[{"id": "tc_002", "name": "Read", "input": {"file_path": "/f"}}],
            stop_reason="tool_use",
        )
        read_msg_3 = mock_anthropic_message(
            text="One more read.",
            tool_uses=[{"id": "tc_003", "name": "Read", "input": {"file_path": "/f"}}],
            stop_reason="tool_use",
        )
        final_msg = mock_anthropic_message(text="All done.", stop_reason="end_turn")
        mock_anthropic_client.messages.create.side_effect = [
            read_msg_1, read_msg_2, read_msg_3, final_msg,
        ]

        tool_responses = [
            ToolResponseConfig(
                match=ToolMatchConfig(tool="Read"),
                responses=[
                    {"content": "version-1"},
                    {"content": "version-2"},
                    {"content": "version-3"},
                ],
            ),
        ]
        executor = MultiTurnExecutor(
            client=mock_anthropic_client,
            config=_config(),
            tool_responses=tool_responses,
        )
        trace = executor.execute("You are helpful.", _input())

        assert trace.turn_count == 4
        assert trace.stop_reason == "end_turn"

        # Verify the tool_result content injected into messages for each turn
        calls = mock_anthropic_client.messages.create.call_args_list
        # Turn 2 messages should have tool_result with version-1
        assert calls[1].kwargs["messages"][2]["content"][0]["content"] == "version-1"
        # Turn 3 messages should have tool_result with version-2
        assert calls[2].kwargs["messages"][4]["content"][0]["content"] == "version-2"
        # Turn 4 messages should have tool_result with version-3
        assert calls[3].kwargs["messages"][6]["content"][0]["content"] == "version-3"
