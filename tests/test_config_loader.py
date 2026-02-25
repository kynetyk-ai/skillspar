"""Tests for config/loader.py — YAML loading."""

import pytest

from skill_evaluator.config.loader import (
    ConfigLoadError,
    _apply_env_defaults,
    load_eval_suite,
    resolve_config,
    resolve_skill_path,
)
from skill_evaluator.config.schema import EvalSuite, SuiteDefaults


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


class TestApplyEnvDefaults:
    def test_env_var_injected_when_yaml_key_absent(self, monkeypatch):
        monkeypatch.setenv("SKILLSPAR_MODEL", "claude-opus-4")
        raw = {"defaults": {}}
        _apply_env_defaults(raw)
        assert raw["defaults"]["model"] == "claude-opus-4"

    def test_yaml_key_preserved_when_present(self, monkeypatch):
        monkeypatch.setenv("SKILLSPAR_MODEL", "claude-opus-4")
        raw = {"defaults": {"model": "yaml-model"}}
        _apply_env_defaults(raw)
        assert raw["defaults"]["model"] == "yaml-model"

    def test_no_env_var_no_change(self, monkeypatch):
        monkeypatch.delenv("SKILLSPAR_MODEL", raising=False)
        monkeypatch.delenv("SKILLSPAR_JUDGE_MODEL", raising=False)
        raw = {"defaults": {}}
        _apply_env_defaults(raw)
        assert "model" not in raw["defaults"]
        assert "judge_model" not in raw["defaults"]

    def test_judge_model_env_injected(self, monkeypatch):
        monkeypatch.setenv("SKILLSPAR_JUDGE_MODEL", "judge-model")
        raw = {"defaults": {}}
        _apply_env_defaults(raw)
        assert raw["defaults"]["judge_model"] == "judge-model"

    def test_judge_model_yaml_preserved(self, monkeypatch):
        monkeypatch.setenv("SKILLSPAR_JUDGE_MODEL", "env-judge")
        raw = {"defaults": {"judge_model": "yaml-judge"}}
        _apply_env_defaults(raw)
        assert raw["defaults"]["judge_model"] == "yaml-judge"

    def test_creates_defaults_key_if_missing(self, monkeypatch):
        monkeypatch.setenv("SKILLSPAR_MODEL", "test-model")
        raw = {}
        _apply_env_defaults(raw)
        assert raw["defaults"]["model"] == "test-model"


class TestResolveConfig:
    def test_cli_overrides_take_precedence(self):
        defaults = SuiteDefaults(runs=1, concurrency=1, model="yaml-model")
        config = resolve_config(
            defaults, cli_runs=5, cli_concurrency=3, cli_model="cli-model",
        )
        assert config.runs == 5
        assert config.concurrency == 3
        assert config.model == "cli-model"

    def test_defaults_flow_through(self):
        defaults = SuiteDefaults(runs=3, concurrency=2, model="yaml-model")
        config = resolve_config(defaults)
        assert config.runs == 3
        assert config.concurrency == 2
        assert config.model == "yaml-model"

    def test_env_output_used_when_cli_none(self, monkeypatch):
        monkeypatch.setenv("SKILLSPAR_OUTPUT", "./results")
        defaults = SuiteDefaults()
        config = resolve_config(defaults, cli_output=None)
        assert config.output == "./results"

    def test_cli_output_overrides_env(self, monkeypatch):
        monkeypatch.setenv("SKILLSPAR_OUTPUT", "./results")
        defaults = SuiteDefaults()
        config = resolve_config(defaults, cli_output="./custom")
        assert config.output == "./custom"

    def test_verbose_and_filter(self):
        defaults = SuiteDefaults()
        config = resolve_config(
            defaults, cli_verbose=True, cli_filter_pattern="greeting",
        )
        assert config.verbose is True
        assert config.filter_pattern == "greeting"

    def test_config_is_frozen(self):
        defaults = SuiteDefaults()
        config = resolve_config(defaults)
        with pytest.raises(Exception):
            config.runs = 10
