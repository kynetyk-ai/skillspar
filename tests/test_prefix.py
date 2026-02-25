"""Tests for engine/prefix.py — prefix loader and validator."""

import pytest

from skill_evaluator.config.schema import ConversationPrefixConfig, MessageConfig
from skill_evaluator.engine.prefix import (
    MINIMUM_CACHE_TOKEN_THRESHOLD,
    PrefixLoadError,
    estimate_prefix_tokens,
    load_prefix_messages,
)


class TestLoadPrefixInline:
    def test_inline_messages_returned(self, tmp_path):
        eval_file = tmp_path / "test.eval.yaml"
        prefix = ConversationPrefixConfig(
            messages=[
                MessageConfig(role="user", content="Hi"),
                MessageConfig(role="assistant", content="Hello!"),
            ]
        )
        result = load_prefix_messages(eval_file, prefix)
        assert len(result) == 2
        assert result[0].role == "user"
        assert result[1].role == "assistant"

    def test_cache_control_tagged_on_last(self, tmp_path):
        eval_file = tmp_path / "test.eval.yaml"
        prefix = ConversationPrefixConfig(
            messages=[
                MessageConfig(role="user", content="Hi"),
                MessageConfig(role="assistant", content="Hello!"),
            ]
        )
        result = load_prefix_messages(eval_file, prefix, enable_caching=True)
        assert result[-1].cache_control == {"type": "ephemeral"}
        assert result[0].cache_control is None

    def test_cache_control_not_tagged_when_disabled(self, tmp_path):
        eval_file = tmp_path / "test.eval.yaml"
        prefix = ConversationPrefixConfig(
            messages=[
                MessageConfig(role="user", content="Hi"),
                MessageConfig(role="assistant", content="Hello!"),
            ]
        )
        result = load_prefix_messages(eval_file, prefix, enable_caching=False)
        assert result[-1].cache_control is None


class TestLoadPrefixExternal:
    def test_external_file_loaded(self, tmp_path):
        prefix_file = tmp_path / "prefix.yaml"
        prefix_file.write_text(
            '- role: user\n  content: "Hey"\n- role: assistant\n  content: "Hi there"\n'
        )
        eval_file = tmp_path / "test.eval.yaml"
        prefix = ConversationPrefixConfig(file="./prefix.yaml")
        result = load_prefix_messages(eval_file, prefix)
        assert len(result) == 2
        assert result[0].content == "Hey"
        assert result[1].content == "Hi there"

    def test_missing_file_raises(self, tmp_path):
        eval_file = tmp_path / "test.eval.yaml"
        prefix = ConversationPrefixConfig(file="./nonexistent.yaml")
        with pytest.raises(PrefixLoadError, match="not found"):
            load_prefix_messages(eval_file, prefix)

    def test_invalid_yaml_raises(self, tmp_path):
        prefix_file = tmp_path / "bad.yaml"
        prefix_file.write_text("{{invalid")
        eval_file = tmp_path / "test.eval.yaml"
        prefix = ConversationPrefixConfig(file="./bad.yaml")
        with pytest.raises(PrefixLoadError, match="Invalid YAML"):
            load_prefix_messages(eval_file, prefix)

    def test_non_list_raises(self, tmp_path):
        prefix_file = tmp_path / "prefix.yaml"
        prefix_file.write_text("key: value\n")
        eval_file = tmp_path / "test.eval.yaml"
        prefix = ConversationPrefixConfig(file="./prefix.yaml")
        with pytest.raises(PrefixLoadError, match="YAML list"):
            load_prefix_messages(eval_file, prefix)

    def test_bad_message_structure_raises(self, tmp_path):
        prefix_file = tmp_path / "prefix.yaml"
        prefix_file.write_text('- role: unknown\n  content: "bad"\n')
        eval_file = tmp_path / "test.eval.yaml"
        prefix = ConversationPrefixConfig(file="./prefix.yaml")
        with pytest.raises(PrefixLoadError, match="Invalid message"):
            load_prefix_messages(eval_file, prefix)


class TestLoadPrefixValidation:
    def test_must_end_with_assistant(self, tmp_path):
        prefix_file = tmp_path / "prefix.yaml"
        prefix_file.write_text('- role: user\n  content: "Hi"\n')
        eval_file = tmp_path / "test.eval.yaml"
        prefix = ConversationPrefixConfig(file="./prefix.yaml")
        with pytest.raises(PrefixLoadError, match="must end with an assistant"):
            load_prefix_messages(eval_file, prefix)

    def test_external_cache_control_tagged(self, tmp_path):
        prefix_file = tmp_path / "prefix.yaml"
        prefix_file.write_text(
            '- role: user\n  content: "Hey"\n- role: assistant\n  content: "Hi there"\n'
        )
        eval_file = tmp_path / "test.eval.yaml"
        prefix = ConversationPrefixConfig(file="./prefix.yaml")
        result = load_prefix_messages(eval_file, prefix, enable_caching=True)
        assert result[-1].cache_control == {"type": "ephemeral"}


class TestEstimatePrefixTokens:
    def test_estimate(self):
        messages = [
            MessageConfig(role="user", content="a" * 100),
            MessageConfig(role="assistant", content="b" * 200),
        ]
        assert estimate_prefix_tokens(messages) == 75  # 300 / 4

    def test_empty_content(self):
        messages = [
            MessageConfig(role="user", content=None),
            MessageConfig(role="assistant", content=""),
        ]
        assert estimate_prefix_tokens(messages) == 0

    def test_threshold_constant(self):
        assert MINIMUM_CACHE_TOKEN_THRESHOLD == 1024
