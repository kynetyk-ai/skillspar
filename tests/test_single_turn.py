"""Tests for engine/single_turn.py — executor with mock client."""


import pytest

from skill_evaluator.config.schema import InputConfig, MessageConfig, ResolvedConfig
from skill_evaluator.engine.single_turn import ExecutionError, SingleTurnExecutor


class TestSingleTurnExecutor:
    def test_execute_returns_trace(self, mock_anthropic_client, mock_anthropic_message):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Hello there!"
        )
        executor = SingleTurnExecutor(mock_anthropic_client, ResolvedConfig())
        input_config = InputConfig(
            messages=[MessageConfig(role="user", content="Hi")]
        )

        trace = executor.execute("You are a helpful assistant.", input_config)

        assert trace.text_output == "Hello there!"
        assert trace.stop_reason == "end_turn"
        assert trace.turn_count == 1
        mock_anthropic_client.messages.create.assert_called_once()

    def test_execute_with_tool_use(self, mock_anthropic_client, mock_anthropic_message):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Creating file.",
            tool_uses=[{"id": "tc_001", "name": "Write", "input": {"file_path": "/x"}}],
            stop_reason="tool_use",
        )
        executor = SingleTurnExecutor(mock_anthropic_client, ResolvedConfig())
        input_config = InputConfig(
            messages=[MessageConfig(role="user", content="Create a file")]
        )

        trace = executor.execute("System prompt", input_config)

        assert trace.tool_names == ["Write"]
        assert trace.stop_reason == "tool_use"

    def test_execute_passes_model_params(self, mock_anthropic_client, mock_anthropic_message):
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message()
        config = ResolvedConfig(model="claude-haiku-4-5-20251001", max_tokens=1024, temperature=0.5)
        executor = SingleTurnExecutor(mock_anthropic_client, config)
        input_config = InputConfig(
            messages=[MessageConfig(role="user", content="Hi")]
        )

        executor.execute("prompt", input_config)

        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
        assert call_kwargs["max_tokens"] == 1024
        assert call_kwargs["temperature"] == 0.5

    def test_api_error_raises_execution_error(self, mock_anthropic_client):
        mock_anthropic_client.messages.create.side_effect = Exception("API timeout")
        executor = SingleTurnExecutor(mock_anthropic_client, ResolvedConfig())
        input_config = InputConfig(
            messages=[MessageConfig(role="user", content="Hi")]
        )

        with pytest.raises(ExecutionError, match="API call failed"):
            executor.execute("prompt", input_config)
