"""Tests for config/schema.py — Pydantic models."""

import pytest
from pydantic import ValidationError

from skill_evaluator.config.schema import (
    AssertionConfig,
    ContextFileConfig,
    EvalSuite,
    MessageConfig,
    MultiTurnTest,
    OutputContainsAssertion,
    OutputMatchesRegexAssertion,
    ResolvedConfig,
    SingleTurnTest,
    StopReasonAssertion,
    SuiteDefaults,
    ToolCalledAssertion,
    ToolNotCalledAssertion,
    ToolResponseConfig,
)


class TestAssertionDiscriminator:
    def test_stop_reason(self):
        from pydantic import TypeAdapter
        ta = TypeAdapter(AssertionConfig)
        result = ta.validate_python({"type": "stop_reason", "value": "end_turn"})
        assert isinstance(result, StopReasonAssertion)
        assert result.value == "end_turn"

    def test_output_contains(self):
        from pydantic import TypeAdapter
        ta = TypeAdapter(AssertionConfig)
        result = ta.validate_python({"type": "output_contains", "value": "hello"})
        assert isinstance(result, OutputContainsAssertion)

    def test_tool_called(self):
        from pydantic import TypeAdapter
        ta = TypeAdapter(AssertionConfig)
        result = ta.validate_python({"type": "tool_called", "tool": "Write"})
        assert isinstance(result, ToolCalledAssertion)

    def test_tool_not_called(self):
        from pydantic import TypeAdapter
        ta = TypeAdapter(AssertionConfig)
        result = ta.validate_python({"type": "tool_not_called", "tool": "Read"})
        assert isinstance(result, ToolNotCalledAssertion)

    def test_invalid_type_raises(self):
        from pydantic import TypeAdapter
        ta = TypeAdapter(AssertionConfig)
        with pytest.raises(ValidationError):
            ta.validate_python({"type": "nonexistent", "value": "x"})


class TestRegexValidation:
    def test_valid_regex(self):
        a = OutputMatchesRegexAssertion(type="output_matches_regex", pattern="(?i)hello|hi")
        assert a.pattern == "(?i)hello|hi"

    def test_invalid_regex_raises(self):
        with pytest.raises(ValidationError, match="Invalid regex"):
            OutputMatchesRegexAssertion(type="output_matches_regex", pattern="[invalid")


class TestMessageConfig:
    def test_user_message(self):
        m = MessageConfig(role="user", content="Hello!")
        assert m.role == "user"
        assert m.content == "Hello!"

    def test_assistant_with_tool_calls(self):
        m = MessageConfig(
            role="assistant",
            content="Sure",
            tool_calls=[{"id": "tc_001", "name": "Write", "input": {"file_path": "/x"}}],
        )
        assert len(m.tool_calls) == 1
        assert m.tool_calls[0].name == "Write"

    def test_tool_result(self):
        m = MessageConfig(role="tool_result", tool_use_id="tc_001", content="OK")
        assert m.role == "tool_result"


class TestEvalSuite:
    def test_minimal_valid_suite(self):
        raw = {
            "suite": "test",
            "skill": "./SKILL.md",
            "tests": [
                {
                    "type": "single_turn",
                    "name": "basic",
                    "input": {"messages": [{"role": "user", "content": "Hi"}]},
                    "assertions": [{"type": "stop_reason", "value": "end_turn"}],
                }
            ],
        }
        suite = EvalSuite.model_validate(raw)
        assert suite.suite == "test"
        assert len(suite.tests) == 1
        assert isinstance(suite.tests[0], SingleTurnTest)

    def test_defaults_are_applied(self):
        raw = {
            "suite": "test",
            "skill": "./SKILL.md",
            "tests": [
                {
                    "type": "single_turn",
                    "name": "basic",
                    "input": {"messages": [{"role": "user", "content": "Hi"}]},
                    "assertions": [],
                }
            ],
        }
        suite = EvalSuite.model_validate(raw)
        assert suite.defaults.model == "claude-sonnet-4-5-20250929"
        assert suite.defaults.max_tokens == 4096

    def test_missing_suite_name_raises(self):
        with pytest.raises(ValidationError):
            EvalSuite.model_validate({"skill": "./SKILL.md", "tests": []})


class TestContextFileConfig:
    def test_valid_file_ref(self):
        c = ContextFileConfig(file="./src/main.py")
        assert c.file == "./src/main.py"
        assert c.lines is None

    def test_valid_lines(self):
        c = ContextFileConfig(file="./f.py", lines=[1, 50])
        assert c.lines == [1, 50]

    def test_wrong_length_raises(self):
        with pytest.raises(ValidationError, match="lines must be"):
            ContextFileConfig(file="./f.py", lines=[1, 2, 3])

    def test_start_less_than_1_raises(self):
        with pytest.raises(ValidationError, match="start must be >= 1"):
            ContextFileConfig(file="./f.py", lines=[0, 10])

    def test_end_less_than_start_raises(self):
        with pytest.raises(ValidationError, match="end must be >= start"):
            ContextFileConfig(file="./f.py", lines=[10, 5])


class TestContextInSuiteAndTests:
    def test_suite_context_parses(self):
        raw = {
            "suite": "test",
            "skill": "./SKILL.md",
            "context": [{"file": "./src/main.py"}, {"file": "./utils.py", "lines": [1, 50]}],
            "tests": [
                {
                    "type": "single_turn",
                    "name": "basic",
                    "input": {"messages": [{"role": "user", "content": "Hi"}]},
                    "assertions": [],
                }
            ],
        }
        suite = EvalSuite.model_validate(raw)
        assert len(suite.context) == 2
        assert suite.context[1].lines == [1, 50]

    def test_test_context_parses(self):
        raw = {
            "suite": "test",
            "skill": "./SKILL.md",
            "tests": [
                {
                    "type": "single_turn",
                    "name": "with context",
                    "context": [{"file": "./handler.py"}],
                    "input": {"messages": [{"role": "user", "content": "Review"}]},
                    "assertions": [],
                }
            ],
        }
        suite = EvalSuite.model_validate(raw)
        test = suite.tests[0]
        assert isinstance(test, SingleTurnTest)
        assert len(test.context) == 1

    def test_no_context_defaults_to_none(self):
        raw = {
            "suite": "test",
            "skill": "./SKILL.md",
            "tests": [
                {
                    "type": "single_turn",
                    "name": "basic",
                    "input": {"messages": [{"role": "user", "content": "Hi"}]},
                    "assertions": [],
                }
            ],
        }
        suite = EvalSuite.model_validate(raw)
        assert suite.context is None
        assert suite.tests[0].context is None


# ---------------------------------------------------------------------------
# New: SuiteDefaults validators + per-test overrides
# ---------------------------------------------------------------------------


class TestSuiteDefaultsNewFields:
    def test_defaults_have_correct_values(self):
        d = SuiteDefaults()
        assert d.runs == 1
        assert d.pass_threshold == 1.0
        assert d.max_retries == 2
        assert d.concurrency == 1

    def test_custom_values_accepted(self):
        d = SuiteDefaults(runs=5, pass_threshold=0.8, max_retries=0, concurrency=4)
        assert d.runs == 5
        assert d.pass_threshold == 0.8
        assert d.max_retries == 0
        assert d.concurrency == 4

    def test_runs_less_than_1_rejected(self):
        with pytest.raises(ValidationError, match="runs must be >= 1"):
            SuiteDefaults(runs=0)

    def test_pass_threshold_zero_rejected(self):
        with pytest.raises(ValidationError, match="pass_threshold"):
            SuiteDefaults(pass_threshold=0.0)

    def test_pass_threshold_above_1_rejected(self):
        with pytest.raises(ValidationError, match="pass_threshold"):
            SuiteDefaults(pass_threshold=1.1)

    def test_pass_threshold_1_accepted(self):
        d = SuiteDefaults(pass_threshold=1.0)
        assert d.pass_threshold == 1.0

    def test_concurrency_less_than_1_rejected(self):
        with pytest.raises(ValidationError, match="concurrency must be >= 1"):
            SuiteDefaults(concurrency=0)

    def test_max_retries_negative_rejected(self):
        with pytest.raises(ValidationError, match="max_retries must be >= 0"):
            SuiteDefaults(max_retries=-1)


class TestPerTestOverrides:
    def test_single_turn_per_test_fields_default(self):
        t = SingleTurnTest(
            type="single_turn",
            name="test",
            input={"messages": [{"role": "user", "content": "Hi"}]},
            assertions=[],
        )
        assert t.runs is None
        assert t.pass_threshold is None
        assert t.baseline is False

    def test_single_turn_per_test_fields_set(self):
        t = SingleTurnTest(
            type="single_turn",
            name="test",
            input={"messages": [{"role": "user", "content": "Hi"}]},
            assertions=[],
            runs=10,
            pass_threshold=0.9,
            baseline=True,
        )
        assert t.runs == 10
        assert t.pass_threshold == 0.9
        assert t.baseline is True

    def test_multi_turn_per_test_fields(self):
        t = MultiTurnTest(
            type="multi_turn",
            name="test",
            input={"messages": [{"role": "user", "content": "Hi"}]},
            assertions=[],
            runs=3,
            pass_threshold=0.5,
            baseline=True,
        )
        assert t.runs == 3
        assert t.pass_threshold == 0.5
        assert t.baseline is True

    def test_none_overrides_accepted(self):
        t = SingleTurnTest(
            type="single_turn",
            name="test",
            input={"messages": [{"role": "user", "content": "Hi"}]},
            assertions=[],
            runs=None,
            pass_threshold=None,
        )
        assert t.runs is None
        assert t.pass_threshold is None

    def test_full_suite_yaml_with_new_fields(self):
        raw = {
            "suite": "test",
            "skill": "./SKILL.md",
            "defaults": {
                "runs": 5,
                "pass_threshold": 0.8,
                "concurrency": 4,
                "max_retries": 3,
            },
            "tests": [
                {
                    "type": "single_turn",
                    "name": "with overrides",
                    "input": {"messages": [{"role": "user", "content": "Hi"}]},
                    "assertions": [{"type": "stop_reason", "value": "end_turn"}],
                    "runs": 10,
                    "pass_threshold": 1.0,
                    "baseline": True,
                }
            ],
        }
        suite = EvalSuite.model_validate(raw)
        assert suite.defaults.runs == 5
        assert suite.defaults.concurrency == 4
        test = suite.tests[0]
        assert isinstance(test, SingleTurnTest)
        assert test.runs == 10
        assert test.baseline is True


class TestToolResponseConfig:
    def test_single_response_accepted(self):
        tr = ToolResponseConfig(match="*", response={"content": "ok"})
        assert tr.response == {"content": "ok"}
        assert tr.responses is None

    def test_responses_list_accepted(self):
        tr = ToolResponseConfig(
            match="*",
            responses=[{"content": "a"}, {"content": "b"}],
        )
        assert tr.response is None
        assert len(tr.responses) == 2

    def test_both_provided_rejected(self):
        with pytest.raises(ValidationError, match="not both"):
            ToolResponseConfig(
                match="*",
                response={"content": "x"},
                responses=[{"content": "y"}],
            )

    def test_neither_provided_rejected(self):
        with pytest.raises(ValidationError, match="required"):
            ToolResponseConfig(match="*")

    def test_empty_responses_rejected(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            ToolResponseConfig(match="*", responses=[])

    def test_get_response_single(self):
        tr = ToolResponseConfig(match="*", response={"content": "always"})
        assert tr.get_response(0) == {"content": "always"}
        assert tr.get_response(5) == {"content": "always"}

    def test_get_response_sequence(self):
        tr = ToolResponseConfig(
            match="*",
            responses=[{"content": "a"}, {"content": "b"}, {"content": "c"}],
        )
        assert tr.get_response(0) == {"content": "a"}
        assert tr.get_response(1) == {"content": "b"}
        assert tr.get_response(2) == {"content": "c"}

    def test_get_response_clamps_to_last(self):
        tr = ToolResponseConfig(
            match="*",
            responses=[{"content": "first"}, {"content": "last"}],
        )
        assert tr.get_response(0) == {"content": "first"}
        assert tr.get_response(1) == {"content": "last"}
        assert tr.get_response(2) == {"content": "last"}
        assert tr.get_response(100) == {"content": "last"}


class TestResolvedConfig:
    def test_defaults(self):
        config = ResolvedConfig()
        assert config.model == "claude-sonnet-4-5-20250929"
        assert config.judge_model == ""
        assert config.max_tokens == 4096
        assert config.temperature == 0
        assert config.runs == 1
        assert config.pass_threshold == 1.0
        assert config.max_retries == 2
        assert config.concurrency == 1
        assert config.output is None
        assert config.output_format == "json"
        assert config.verbose is False
        assert config.filter_pattern is None

    def test_frozen(self):
        config = ResolvedConfig()
        with pytest.raises(Exception):
            config.model = "new-model"

    def test_custom_values(self):
        config = ResolvedConfig(
            model="custom-model",
            runs=5,
            concurrency=3,
            output="./out",
            output_format="junit",
            verbose=True,
            filter_pattern="test_*",
        )
        assert config.model == "custom-model"
        assert config.runs == 5
        assert config.concurrency == 3
        assert config.output == "./out"
        assert config.output_format == "junit"
        assert config.verbose is True
        assert config.filter_pattern == "test_*"
