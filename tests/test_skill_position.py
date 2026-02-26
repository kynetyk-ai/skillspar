"""Tests for conversation_prefix.skill_position — message ordering and caching."""

import pytest
from pydantic import ValidationError

from skill_evaluator.config.loader import load_eval_suite
from skill_evaluator.config.schema import (
    ConversationPrefixConfig,
    MessageConfig,
)
from skill_evaluator.engine.conversation import build_skill_messages
from skill_evaluator.runner import SuiteRunner

# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSkillPositionSchema:
    def test_default_is_top(self):
        cfg = ConversationPrefixConfig(
            messages=[
                MessageConfig(role="user", content="Hi"),
                MessageConfig(role="assistant", content="Hello!"),
            ]
        )
        assert cfg.skill_position == "top"

    def test_bottom_accepted(self):
        cfg = ConversationPrefixConfig(
            skill_position="bottom",
            messages=[
                MessageConfig(role="user", content="Hi"),
                MessageConfig(role="assistant", content="Hello!"),
            ],
        )
        assert cfg.skill_position == "bottom"

    def test_invalid_position_rejected(self):
        with pytest.raises(ValidationError):
            ConversationPrefixConfig(
                skill_position="invalid",
                messages=[
                    MessageConfig(role="user", content="Hi"),
                    MessageConfig(role="assistant", content="Hello!"),
                ],
            )


# ---------------------------------------------------------------------------
# build_skill_messages cache_control tests
# ---------------------------------------------------------------------------


class TestBuildSkillMessagesCache:
    def test_no_cache_by_default(self):
        msgs = build_skill_messages("some skill body")
        assert msgs[0].cache_control is None

    def test_cache_control_passed_through(self):
        msgs = build_skill_messages("some skill body", cache_control={"type": "ephemeral"})
        assert msgs[0].cache_control == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# Runner integration — message ordering and caching
# ---------------------------------------------------------------------------


def _make_suite_files(tmp_path, skill_position=None):
    """Create minimal eval suite files with optional skill_position."""
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nYou are a helpful test skill.")

    sp_line = ""
    if skill_position:
        sp_line = f"  skill_position: {skill_position}"

    yaml_content = f"""\
suite: "skill position test"
skill: "./skills/SKILL.md"
defaults:
  model: claude-sonnet-4-5-20250929
  max_tokens: 1024
  temperature: 0
  enable_caching: true

conversation_prefix:
{sp_line}
  messages:
    - role: user
      content: "Prior user message"
    - role: assistant
      content: "Prior assistant reply"

tests:
  - type: single_turn
    name: "ordering test"
    input:
      messages:
        - role: user
          content: "Test question"
    assertions:
      - type: stop_reason
        value: end_turn
"""
    eval_file = tmp_path / "test.eval.yaml"
    eval_file.write_text(yaml_content)
    return eval_file


def _get_api_messages(mock_client):
    """Extract messages from the mock client's create call."""
    call_kwargs = mock_client.messages.create.call_args
    return call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")


def _flatten_text(msg):
    """Extract all text content from an API message."""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    return " ".join(
        block.get("text", "") for block in content if isinstance(block, dict) and "text" in block
    )


class TestTopMode:
    """Default mode (top): Skill → Prefix → Test.

    Note: consecutive user messages (skill + prefix-user) get coalesced by
    build_messages, so the API sees 3 messages not 4.
    """

    def test_message_order(self, tmp_path, mock_anthropic_client, mock_anthropic_message):
        eval_file = _make_suite_files(tmp_path)  # default = top
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hi")

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        messages = _get_api_messages(mock_anthropic_client)
        texts = [_flatten_text(m) for m in messages]

        # After coalescing: [skill+prefix-user, prefix-assistant, test-user]
        assert "skill has been activated" in texts[0]
        assert "Prior user message" in texts[0]  # coalesced with skill
        assert "Prior assistant reply" in texts[1]
        assert "Test question" in texts[2]

    def test_skill_message_has_cache_control(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        eval_file = _make_suite_files(tmp_path)
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hi")

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        messages = _get_api_messages(mock_anthropic_client)
        # First message (coalesced user) should contain a block with cache_control
        # from the skill message
        first_content = messages[0]["content"]
        assert isinstance(first_content, list)
        skill_block = first_content[0]
        assert skill_block.get("cache_control") == {"type": "ephemeral"}

    def test_last_prefix_message_has_cache_control(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        eval_file = _make_suite_files(tmp_path)
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hi")

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        messages = _get_api_messages(mock_anthropic_client)
        # The assistant prefix message (index 1) should have cache_control
        assistant_msg = messages[1]
        assert assistant_msg["role"] == "assistant"
        content = assistant_msg["content"]
        assert isinstance(content, list)
        assert content[-1].get("cache_control") == {"type": "ephemeral"}


class TestBottomMode:
    """Bottom mode: Prefix → Skill → Test.

    Note: prefix-assistant ends with assistant role, then skill is a user message,
    so no coalescing between prefix and skill. But skill-user + test-user
    will coalesce.
    """

    def test_message_order(self, tmp_path, mock_anthropic_client, mock_anthropic_message):
        eval_file = _make_suite_files(tmp_path, skill_position="bottom")
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hi")

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        messages = _get_api_messages(mock_anthropic_client)
        texts = [_flatten_text(m) for m in messages]

        # After coalescing: [prefix-user, prefix-assistant, skill+test-user]
        assert "Prior user message" in texts[0]
        assert "Prior assistant reply" in texts[1]
        assert "skill has been activated" in texts[2]
        assert "Test question" in texts[2]  # coalesced with skill

    def test_skill_message_has_cache_control(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        eval_file = _make_suite_files(tmp_path, skill_position="bottom")
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hi")

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        messages = _get_api_messages(mock_anthropic_client)
        # Skill+test coalesced message (index 2) should contain cache_control
        # on the skill block (first block)
        content = messages[2]["content"]
        assert isinstance(content, list)
        skill_block = content[0]
        assert skill_block.get("cache_control") == {"type": "ephemeral"}

    def test_last_prefix_message_has_cache_control(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        """In bottom mode, the last prefix message gets cache_control as a shared
        breakpoint across skill and baseline runs."""
        eval_file = _make_suite_files(tmp_path, skill_position="bottom")
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hi")

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        messages = _get_api_messages(mock_anthropic_client)
        # Prefix user message (index 0) — no cache_control
        assert "cache_control" not in str(messages[0])
        # Prefix assistant message (index 1) — last prefix msg gets cache_control
        assistant_content = messages[1]["content"]
        assert isinstance(assistant_content, list)
        assert assistant_content[-1].get("cache_control") == {"type": "ephemeral"}


class TestNoPrefixNoSkillCache:
    """Without a conversation_prefix, skill messages should not get cache_control."""

    def test_no_prefix_no_skill_cache(
        self, tmp_path, mock_anthropic_client, mock_anthropic_message
    ):
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nSkill body")

        yaml_content = """\
suite: "no prefix test"
skill: "./skills/SKILL.md"
defaults:
  model: claude-sonnet-4-5-20250929
  enable_caching: true

tests:
  - type: single_turn
    name: "basic"
    input:
      messages:
        - role: user
          content: "Hello"
    assertions:
      - type: stop_reason
        value: end_turn
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)
        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(text="Hi")

        suite = load_eval_suite(eval_file)
        runner = SuiteRunner(eval_file, suite, client=mock_anthropic_client)
        runner.run()

        messages = _get_api_messages(mock_anthropic_client)
        # Skill message should NOT have cache_control
        first_content = messages[0]
        if isinstance(first_content.get("content"), list):
            for block in first_content["content"]:
                assert block.get("cache_control") is None
        # String content has no cache_control
