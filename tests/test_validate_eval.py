"""Tests for the eval YAML validation script (standalone, no skill_evaluator imports)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Import from the script — adjust path so it's importable
_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "skills" / "evaluate-skill" / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

from validate_eval import (  # noqa: E402
    _levenshtein,
    _path,
    _suggest_typo,
    validate_eval_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(tmp_path: Path, data: dict) -> Path:
    """Write a dict as YAML to a temp file and return the path."""
    p = tmp_path / "test.eval.yaml"
    p.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return p


def _minimal_suite(**overrides) -> dict:
    """Return a minimal valid suite dict, with optional overrides merged."""
    base = {
        "suite": "test suite",
        "skill": "./SKILL.md",
        "tests": [
            {
                "type": "single_turn",
                "name": "basic test",
                "input": {"messages": [{"role": "user", "content": "Hello"}]},
                "assertions": [{"type": "stop_reason", "value": "end_turn"}],
            }
        ],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------


class TestPath:
    def test_simple_path(self):
        assert _path("tests", 0, "name") == "tests[0].name"

    def test_nested_path(self):
        assert _path("tests", 2, "assertions", 1, "type") == "tests[2].assertions[1].type"

    def test_top_level(self):
        assert _path("suite") == "suite"


class TestLevenshtein:
    def test_identical(self):
        assert _levenshtein("abc", "abc") == 0

    def test_one_edit(self):
        assert _levenshtein("abc", "ab") == 1

    def test_swap(self):
        assert _levenshtein("responce", "response") == 1

    def test_empty(self):
        assert _levenshtein("", "abc") == 3


class TestSuggestTypo:
    def test_close_match(self):
        assert _suggest_typo("responce", ["response", "request"]) == "response"

    def test_no_match(self):
        assert _suggest_typo("zzzzzzz", ["response", "request"]) is None

    def test_case_insensitive(self):
        assert _suggest_typo("Output_Contains", ["output_contains", "output_not_contains"]) == "output_contains"


# ---------------------------------------------------------------------------
# Schema errors: discriminator / test type
# ---------------------------------------------------------------------------


class TestDiscriminatorErrors:
    def test_invalid_test_type(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "single",
            "name": "bad",
            "input": {"messages": [{"role": "user", "content": "Hi"}]},
            "assertions": [],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "invalid test type" in msg
        assert "single_turn" in msg
        assert "multi_turn" in msg

    def test_invalid_assertion_type(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "single_turn",
            "name": "bad assertion",
            "input": {"messages": [{"role": "user", "content": "Hi"}]},
            "assertions": [{"type": "contains", "value": "x"}],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "unknown assertion type" in msg
        assert "output_contains" in msg


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------


class TestMissingFields:
    def test_missing_suite_name(self, tmp_path):
        raw = {"skill": "./SKILL.md", "tests": []}
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "missing required field" in msg.lower() or "missing" in msg.lower()

    def test_missing_input(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "single_turn",
            "name": "no input",
            "assertions": [{"type": "stop_reason", "value": "end_turn"}],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "input" in msg.lower()

    def test_missing_test_name(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "single_turn",
            "input": {"messages": [{"role": "user", "content": "Hi"}]},
            "assertions": [],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "missing" in msg.lower()

    def test_missing_assertion_type(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "single_turn",
            "name": "no assertion type",
            "input": {"messages": [{"role": "user", "content": "Hi"}]},
            "assertions": [{"value": "hello"}],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "type" in msg.lower()

    def test_missing_messages_in_input(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "single_turn",
            "name": "no messages",
            "input": {},
            "assertions": [],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "messages" in msg.lower()

    def test_missing_assertion_required_field(self, tmp_path):
        """output_contains requires a 'value' field."""
        raw = _minimal_suite(tests=[{
            "type": "single_turn",
            "name": "missing value",
            "input": {"messages": [{"role": "user", "content": "Hi"}]},
            "assertions": [{"type": "output_contains"}],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "value" in msg.lower()


# ---------------------------------------------------------------------------
# Invalid values
# ---------------------------------------------------------------------------


class TestInvalidValues:
    def test_runs_zero(self, tmp_path):
        raw = _minimal_suite(defaults={"runs": 0})
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "runs" in msg.lower()

    def test_pass_threshold_too_high(self, tmp_path):
        raw = _minimal_suite(defaults={"pass_threshold": 2.0})
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "pass_threshold" in msg.lower()

    def test_invalid_regex(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "single_turn",
            "name": "bad regex",
            "input": {"messages": [{"role": "user", "content": "Hi"}]},
            "assertions": [{"type": "output_matches_regex", "pattern": "[invalid"}],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "regex" in msg.lower() or "pattern" in msg.lower()

    def test_invalid_message_role(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "single_turn",
            "name": "bad role",
            "input": {"messages": [{"role": "system", "content": "Hi"}]},
            "assertions": [],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "invalid message role" in msg.lower()

    def test_concurrency_zero(self, tmp_path):
        raw = _minimal_suite(defaults={"concurrency": 0})
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "concurrency" in msg.lower()

    def test_max_retries_negative(self, tmp_path):
        raw = _minimal_suite(defaults={"max_retries": -1})
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "max_retries" in msg.lower()


# ---------------------------------------------------------------------------
# Tool response errors
# ---------------------------------------------------------------------------


class TestToolResponseErrors:
    def test_both_response_and_responses(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "multi_turn",
            "name": "both",
            "input": {"messages": [{"role": "user", "content": "Hi"}]},
            "tool_responses": [{
                "match": "*",
                "response": {"content": "a"},
                "responses": [{"content": "b"}],
            }],
            "assertions": [],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "not both" in msg.lower()

    def test_neither_response_nor_responses(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "multi_turn",
            "name": "neither",
            "input": {"messages": [{"role": "user", "content": "Hi"}]},
            "tool_responses": [{"match": "*"}],
            "assertions": [],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "required" in msg.lower()

    def test_empty_responses_list(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "multi_turn",
            "name": "empty",
            "input": {"messages": [{"role": "user", "content": "Hi"}]},
            "tool_responses": [{"match": "*", "responses": []}],
            "assertions": [],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "empty" in msg.lower()


# ---------------------------------------------------------------------------
# Conversation prefix errors
# ---------------------------------------------------------------------------


class TestConversationPrefixErrors:
    def test_prefix_not_ending_with_assistant(self, tmp_path):
        raw = _minimal_suite(conversation_prefix={
            "messages": [{"role": "user", "content": "Hi"}]
        })
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "assistant" in msg.lower()

    def test_both_messages_and_file(self, tmp_path):
        raw = _minimal_suite(conversation_prefix={
            "messages": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"},
            ],
            "file": "./prefix.yaml",
        })
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "not both" in msg.lower()

    def test_neither_messages_nor_file(self, tmp_path):
        raw = _minimal_suite(conversation_prefix={})
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "required" in msg.lower()

    def test_empty_messages(self, tmp_path):
        raw = _minimal_suite(conversation_prefix={"messages": []})
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "empty" in msg.lower()


# ---------------------------------------------------------------------------
# Semantic checks (warnings on valid files)
# ---------------------------------------------------------------------------


class TestSemanticChecks:
    def test_tool_result_without_matching_id(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "single_turn",
            "name": "orphan tool_result",
            "input": {"messages": [
                {"role": "user", "content": "Hi"},
                {"role": "tool_result", "tool_use_id": "tc_999", "content": "OK"},
            ]},
            "assertions": [],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert ok  # schema is valid, but we get warnings
        assert "tc_999" in msg
        assert "warning" in msg.lower()

    def test_tool_result_with_matching_id_no_warning(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "single_turn",
            "name": "matched tool_result",
            "input": {"messages": [
                {"role": "user", "content": "Do something"},
                {"role": "assistant", "content": "OK", "tool_calls": [
                    {"id": "tc_001", "name": "Write", "input": {"path": "/x"}}
                ]},
                {"role": "tool_result", "tool_use_id": "tc_001", "content": "Done"},
                {"role": "user", "content": "Great"},
            ]},
            "assertions": [],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert ok
        assert "warning" not in msg.lower()

    def test_undeclared_tool_in_assertion(self, tmp_path):
        raw = _minimal_suite(
            tools=[{"builtin": "Read"}],
            tests=[{
                "type": "single_turn",
                "name": "uses Write",
                "input": {"messages": [{"role": "user", "content": "Hi"}]},
                "assertions": [{"type": "tool_called", "tool": "Write"}],
            }],
        )
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert ok
        assert "Write" in msg
        assert "not declared" in msg

    def test_undeclared_tool_in_sequence(self, tmp_path):
        raw = _minimal_suite(
            tools=[{"builtin": "Read"}],
            tests=[{
                "type": "single_turn",
                "name": "sequence with unknown",
                "input": {"messages": [{"role": "user", "content": "Hi"}]},
                "assertions": [{"type": "tool_sequence", "tools": ["Read", "Execute"]}],
            }],
        )
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert ok
        assert "Execute" in msg
        assert "not declared" in msg

    def test_no_tools_declared_skips_check(self, tmp_path):
        """When no tools: section exists, don't warn about tool assertions."""
        raw = _minimal_suite(tests=[{
            "type": "single_turn",
            "name": "tool assert without tools section",
            "input": {"messages": [{"role": "user", "content": "Hi"}]},
            "assertions": [{"type": "tool_called", "tool": "Anything"}],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert ok
        assert "not declared" not in msg

    def test_multi_turn_without_tool_responses(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "multi_turn",
            "name": "no tool_responses",
            "input": {"messages": [{"role": "user", "content": "Hi"}]},
            "assertions": [],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert ok
        assert "multi_turn test with no tool_responses" in msg

    def test_short_llm_judge_criteria(self, tmp_path):
        raw = _minimal_suite(tests=[{
            "type": "single_turn",
            "name": "short judge",
            "input": {"messages": [{"role": "user", "content": "Hi"}]},
            "assertions": [{"type": "llm_judge", "criteria": "good"}],
        }])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert ok
        assert "very short" in msg


# ---------------------------------------------------------------------------
# Success output
# ---------------------------------------------------------------------------


class TestSuccessOutput:
    def test_valid_suite_passes(self, tmp_path):
        raw = _minimal_suite()
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert ok
        assert "VALIDATION PASSED" in msg
        assert "test suite" in msg
        assert "1 tests" in msg or "1 test" in msg

    def test_success_shows_assertion_distribution(self, tmp_path):
        raw = _minimal_suite(tests=[
            {
                "type": "single_turn",
                "name": "test 1",
                "input": {"messages": [{"role": "user", "content": "Hi"}]},
                "assertions": [
                    {"type": "output_contains", "value": "x"},
                    {"type": "output_contains", "value": "y"},
                    {"type": "stop_reason", "value": "end_turn"},
                ],
            },
            {
                "type": "single_turn",
                "name": "test 2",
                "input": {"messages": [{"role": "user", "content": "Hello"}]},
                "assertions": [{"type": "output_contains", "value": "z"}],
            },
        ])
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert ok
        assert "VALIDATION PASSED" in msg
        assert "output_contains: 3" in msg
        assert "stop_reason: 1" in msg


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_file_not_found(self, tmp_path):
        ok, msg = validate_eval_file(tmp_path / "nonexistent.yaml")
        assert not ok
        assert "not found" in msg.lower()

    def test_invalid_yaml_syntax(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("{{invalid yaml: [", encoding="utf-8")
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "YAML" in msg

    def test_yaml_is_not_mapping(self, tmp_path):
        p = tmp_path / "list.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "mapping" in msg.lower()

    def test_multiple_errors(self, tmp_path):
        raw = {
            "skill": "./SKILL.md",
            # missing suite
            "tests": [{
                "type": "invalid_type",
                "name": "broken",
                "input": {"messages": [{"role": "user", "content": "Hi"}]},
                "assertions": [],
            }],
        }
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert not ok
        assert "VALIDATION FAILED" in msg
        assert "Error 1/" in msg

    def test_valid_multi_turn_passes(self, tmp_path):
        raw = _minimal_suite(
            tools=[{"builtin": "Read"}, {"builtin": "Write"}],
            tests=[{
                "type": "multi_turn",
                "name": "read then write",
                "input": {"messages": [{"role": "user", "content": "Read and modify"}]},
                "tool_responses": [
                    {"match": {"tool": "Read"}, "response": {"content": "file contents"}},
                    {"match": {"tool": "Write"}, "response": {"content": "ok"}},
                ],
                "assertions": [
                    {"type": "tool_sequence", "tools": ["Read", "Write"]},
                ],
            }],
        )
        p = _write_yaml(tmp_path, raw)
        ok, msg = validate_eval_file(p)
        assert ok
        assert "VALIDATION PASSED" in msg
