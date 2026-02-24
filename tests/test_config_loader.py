"""Tests for config/loader.py — YAML loading."""

import pytest

from skill_evaluator.config.loader import ConfigLoadError, load_eval_suite, resolve_skill_path
from skill_evaluator.config.schema import EvalSuite


class TestResolveSkillPath:
    def test_resolves_relative_path(self, tmp_path):
        eval_file = tmp_path / "suite.eval.yaml"
        result = resolve_skill_path(eval_file, "./skills/SKILL.md")
        assert result == (tmp_path / "skills" / "SKILL.md").resolve()


class TestLoadEvalSuite:
    def test_load_valid_suite(self, tmp_path):
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: test\n---\nBody")

        yaml_content = """
suite: "test suite"
skill: "./SKILL.md"
tests:
  - type: single_turn
    name: "basic test"
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

        suite = load_eval_suite(eval_file)
        assert isinstance(suite, EvalSuite)
        assert suite.suite == "test suite"
        assert len(suite.tests) == 1

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(ConfigLoadError, match="not found"):
            load_eval_suite(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises(self, tmp_path):
        eval_file = tmp_path / "bad.yaml"
        eval_file.write_text("{{invalid yaml")
        with pytest.raises(ConfigLoadError, match="Invalid YAML"):
            load_eval_suite(eval_file)

    def test_not_a_mapping_raises(self, tmp_path):
        eval_file = tmp_path / "list.yaml"
        eval_file.write_text("- item1\n- item2")
        with pytest.raises(ConfigLoadError, match="mapping"):
            load_eval_suite(eval_file)

    def test_validation_error_raises(self, tmp_path):
        eval_file = tmp_path / "bad.yaml"
        eval_file.write_text("suite: test\nskill: ./SKILL.md\n")
        with pytest.raises(ConfigLoadError, match="Validation"):
            load_eval_suite(eval_file)

    def test_missing_skill_file_raises(self, tmp_path):
        yaml_content = """
suite: "test"
skill: "./missing-SKILL.md"
tests:
  - type: single_turn
    name: "test"
    input:
      messages:
        - role: user
          content: "Hi"
    assertions: []
"""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text(yaml_content)
        with pytest.raises(ConfigLoadError, match="Skill file not found"):
            load_eval_suite(eval_file)
