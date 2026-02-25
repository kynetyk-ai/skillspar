"""Tests for executor.py — execute_suite() high-level API."""

from skill_evaluator.config.loader import load_eval_suite, resolve_config
from skill_evaluator.executor import execute_suite


class TestExecuteSuite:
    def test_smoke(self, tmp_path, mock_anthropic_client, mock_anthropic_message):
        """execute_suite returns a SuiteResult without CLI concerns."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nYou are helpful.")

        yaml_content = """
suite: "executor test"
skill: "./skills/SKILL.md"
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

        mock_anthropic_client.messages.create.return_value = mock_anthropic_message(
            text="Hello!"
        )

        suite = load_eval_suite(eval_file)
        config = resolve_config(suite.defaults)

        # Monkeypatch the Anthropic client via runner
        from unittest.mock import patch
        with patch("skill_evaluator.runner.Anthropic", return_value=mock_anthropic_client):
            result = execute_suite(eval_file, suite, config)

        assert result.suite_name == "executor test"
        assert len(result.test_results) == 1
        assert result.all_passed is True
