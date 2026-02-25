"""Tests for engine/conversation.py — message format conversion."""

from skill_evaluator.config.schema import MessageConfig, ToolCallConfig
from skill_evaluator.engine.conversation import build_messages


class TestBuildMessages:
    def test_simple_user_message(self):
        messages = [MessageConfig(role="user", content="Hello")]
        result = build_messages(messages)
        assert result == [{"role": "user", "content": "Hello"}]

    def test_assistant_text_only(self):
        messages = [
            MessageConfig(role="user", content="Hi"),
            MessageConfig(role="assistant", content="Hello!"),
        ]
        result = build_messages(messages)
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == [{"type": "text", "text": "Hello!"}]

    def test_assistant_with_tool_calls(self):
        messages = [
            MessageConfig(role="user", content="Create a file"),
            MessageConfig(
                role="assistant",
                content="Sure",
                tool_calls=[
                    ToolCallConfig(id="tc_001", name="Write", input={"file_path": "/x"}),
                ],
            ),
        ]
        result = build_messages(messages)
        assistant_msg = result[1]
        assert assistant_msg["role"] == "assistant"
        assert len(assistant_msg["content"]) == 2
        assert assistant_msg["content"][0] == {"type": "text", "text": "Sure"}
        assert assistant_msg["content"][1]["type"] == "tool_use"
        assert assistant_msg["content"][1]["name"] == "Write"

    def test_tool_result_message(self):
        messages = [
            MessageConfig(role="user", content="Create file"),
            MessageConfig(
                role="assistant",
                content="OK",
                tool_calls=[ToolCallConfig(id="tc_001", name="Write", input={})],
            ),
            MessageConfig(role="tool_result", tool_use_id="tc_001", content="Done"),
        ]
        result = build_messages(messages)
        assert len(result) == 3
        tool_result_msg = result[2]
        assert tool_result_msg["role"] == "user"
        assert tool_result_msg["content"][0]["type"] == "tool_result"
        assert tool_result_msg["content"][0]["tool_use_id"] == "tc_001"

    def test_full_conversation_history(self):
        """Test the multi-turn.eval.yaml 'continues from prior context' pattern."""
        messages = [
            MessageConfig(role="user", content="Create a greeting file"),
            MessageConfig(
                role="assistant",
                content="I'll create that for you.",
                tool_calls=[
                    ToolCallConfig(
                        id="tc_001",
                        name="Write",
                        input={"file_path": "/project/greeting.txt", "content": "Hello!"},
                    ),
                ],
            ),
            MessageConfig(role="tool_result", tool_use_id="tc_001", content="File written"),
            MessageConfig(role="user", content="Now add a goodbye message"),
        ]
        result = build_messages(messages)
        # Coalesce merges the tool_result user msg with the following user msg
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert result[2]["role"] == "user"  # tool_result + plain user merged


class TestCacheControlPropagation:
    def test_user_message_with_cache_control(self):
        messages = [
            MessageConfig(role="user", content="Hello", cache_control={"type": "ephemeral"}),
        ]
        result = build_messages(messages)
        assert result[0]["role"] == "user"
        assert isinstance(result[0]["content"], list)
        assert result[0]["content"][0]["type"] == "text"
        assert result[0]["content"][0]["text"] == "Hello"
        assert result[0]["content"][0]["cache_control"] == {"type": "ephemeral"}

    def test_assistant_message_with_cache_control(self):
        messages = [
            MessageConfig(role="user", content="Hi"),
            MessageConfig(
                role="assistant",
                content="Hello!",
                cache_control={"type": "ephemeral"},
            ),
        ]
        result = build_messages(messages)
        assistant_msg = result[1]
        assert assistant_msg["content"][-1]["cache_control"] == {"type": "ephemeral"}

    def test_user_without_cache_control_stays_string(self):
        messages = [MessageConfig(role="user", content="Hello")]
        result = build_messages(messages)
        assert result[0]["content"] == "Hello"

    def test_cache_control_survives_coalescing(self):
        """cache_control on a user message survives when merged with another user."""
        messages = [
            MessageConfig(role="user", content="Part 1", cache_control={"type": "ephemeral"}),
            MessageConfig(role="user", content="Part 2"),
        ]
        result = build_messages(messages)
        assert len(result) == 1  # coalesced
        content = result[0]["content"]
        assert isinstance(content, list)
        # First block should have cache_control from the first message
        assert content[0]["cache_control"] == {"type": "ephemeral"}
        assert content[1]["text"] == "Part 2"


class TestCoalesceConsecutiveRoles:
    def test_tool_result_and_plain_user_merged(self):
        """tool_result (user) followed by plain user → single user message."""
        messages = [
            MessageConfig(role="user", content="Setup"),
            MessageConfig(
                role="assistant",
                content="OK",
                tool_calls=[ToolCallConfig(id="tc_001", name="Read", input={})],
            ),
            MessageConfig(role="tool_result", tool_use_id="tc_001", content="file content"),
            MessageConfig(role="user", content="Now do the task"),
        ]
        result = build_messages(messages)
        assert len(result) == 3
        merged = result[2]
        assert merged["role"] == "user"
        assert isinstance(merged["content"], list)
        # First block is the tool_result, second is the text
        assert merged["content"][0]["type"] == "tool_result"
        assert merged["content"][1]["type"] == "text"
        assert merged["content"][1]["text"] == "Now do the task"

    def test_alternating_roles_unchanged(self):
        messages = [
            MessageConfig(role="user", content="Hi"),
            MessageConfig(role="assistant", content="Hello"),
            MessageConfig(role="user", content="Bye"),
        ]
        result = build_messages(messages)
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert result[2]["role"] == "user"

    def test_text_content_normalized_to_list(self):
        """When merging, string content is normalized to list format."""
        messages = [
            MessageConfig(role="user", content="Setup"),
            MessageConfig(
                role="assistant",
                content="OK",
                tool_calls=[ToolCallConfig(id="tc_001", name="Read", input={})],
            ),
            MessageConfig(role="tool_result", tool_use_id="tc_001", content="data"),
            MessageConfig(role="user", content="Next step"),
        ]
        result = build_messages(messages)
        merged = result[2]
        # All blocks should be dicts in a list
        assert all(isinstance(block, dict) for block in merged["content"])
