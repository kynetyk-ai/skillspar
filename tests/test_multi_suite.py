"""Tests for the multi-suite runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
from skill_evaluator.config.loader import ConfigLoadError
from skill_evaluator.config.schema import (
    EvalSuite,
    InputConfig,
    MessageConfig,
    OutputContainsAssertion,
    SingleTurnTest,
    SuiteDefaults,
)
from skill_evaluator.multi_suite import MultiSuiteResult, SuiteOutcome, run_suites
from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup
from skill_evaluator.skill.parser import SkillParseError


def _make_suite(name="test-suite"):
    return EvalSuite(
        suite=name,
        skill="./SKILL.md",
        defaults=SuiteDefaults(),
        tests=[
            SingleTurnTest(
                type="single_turn",
                name="basic",
                input=InputConfig(messages=[MessageConfig(role="user", content="hello")]),
                assertions=[OutputContainsAssertion(type="output_contains", value="hi")],
            )
        ],
    )


def _make_suite_result(name="test-suite", passed=True):
    status = AssertionStatus.PASSED if passed else AssertionStatus.FAILED
    return SuiteResult(
        suite_name=name,
        test_results=[
            TestRunGroup(
                test_name="basic",
                runs=[
                    TestResult(
                        test_name="basic",
                        assertion_results=[
                            AssertionResult(
                                status=status,
                                assertion_type="output_contains",
                                message="ok" if passed else "fail",
                            )
                        ],
                    )
                ],
            )
        ],
    )


class TestSuiteOutcome:
    def test_passed_when_all_pass(self):
        outcome = SuiteOutcome(
            eval_file=Path("test.eval.yaml"),
            suite=_make_suite(),
            suite_result=_make_suite_result(passed=True),
        )
        assert outcome.passed is True

    def test_failed_when_tests_fail(self):
        outcome = SuiteOutcome(
            eval_file=Path("test.eval.yaml"),
            suite=_make_suite(),
            suite_result=_make_suite_result(passed=False),
        )
        assert outcome.passed is False

    def test_failed_when_error(self):
        outcome = SuiteOutcome(
            eval_file=Path("test.eval.yaml"),
            error="config error",
        )
        assert outcome.passed is False

    def test_suite_name_from_suite(self):
        outcome = SuiteOutcome(
            eval_file=Path("test.eval.yaml"),
            suite=_make_suite("my suite"),
        )
        assert outcome.suite_name == "my suite"

    def test_suite_name_fallback_to_stem(self):
        outcome = SuiteOutcome(eval_file=Path("my-suite.eval.yaml"))
        assert outcome.suite_name == "my-suite.eval"


class TestMultiSuiteResult:
    def test_all_passed(self):
        result = MultiSuiteResult(
            outcomes=[
                SuiteOutcome(
                    eval_file=Path("a.yaml"),
                    suite=_make_suite(),
                    suite_result=_make_suite_result(passed=True),
                ),
                SuiteOutcome(
                    eval_file=Path("b.yaml"),
                    suite=_make_suite(),
                    suite_result=_make_suite_result(passed=True),
                ),
            ]
        )
        assert result.all_passed is True
        assert result.total_suites == 2
        assert result.passed_suites == 2
        assert result.failed_suites == 0
        assert result.error_suites == 0

    def test_one_failed(self):
        result = MultiSuiteResult(
            outcomes=[
                SuiteOutcome(
                    eval_file=Path("a.yaml"),
                    suite=_make_suite(),
                    suite_result=_make_suite_result(passed=True),
                ),
                SuiteOutcome(
                    eval_file=Path("b.yaml"),
                    suite=_make_suite(),
                    suite_result=_make_suite_result(passed=False),
                ),
            ]
        )
        assert result.all_passed is False
        assert result.passed_suites == 1
        assert result.failed_suites == 1

    def test_error_suite(self):
        result = MultiSuiteResult(
            outcomes=[
                SuiteOutcome(
                    eval_file=Path("a.yaml"),
                    suite=_make_suite(),
                    suite_result=_make_suite_result(passed=True),
                ),
                SuiteOutcome(eval_file=Path("b.yaml"), error="bad config"),
            ]
        )
        assert result.all_passed is False
        assert result.error_suites == 1
        assert result.has_config_errors is True


class TestRunSuites:
    @patch("skill_evaluator.multi_suite.execute_suite")
    @patch("skill_evaluator.multi_suite.load_eval_suite")
    def test_two_passing_suites(self, mock_load, mock_execute, tmp_path):
        f1 = tmp_path / "a.eval.yaml"
        f2 = tmp_path / "b.eval.yaml"
        f1.touch()
        f2.touch()

        mock_load.side_effect = [_make_suite("suite-a"), _make_suite("suite-b")]
        mock_execute.side_effect = [
            _make_suite_result("suite-a", passed=True),
            _make_suite_result("suite-b", passed=True),
        ]

        result = run_suites([f1, f2])

        assert result.total_suites == 2
        assert result.all_passed is True
        assert mock_execute.call_count == 2

    @patch("skill_evaluator.multi_suite.execute_suite")
    @patch("skill_evaluator.multi_suite.load_eval_suite")
    def test_one_failing_suite(self, mock_load, mock_execute, tmp_path):
        f1 = tmp_path / "a.eval.yaml"
        f2 = tmp_path / "b.eval.yaml"
        f1.touch()
        f2.touch()

        mock_load.side_effect = [_make_suite("suite-a"), _make_suite("suite-b")]
        mock_execute.side_effect = [
            _make_suite_result("suite-a", passed=True),
            _make_suite_result("suite-b", passed=False),
        ]

        result = run_suites([f1, f2])

        assert result.all_passed is False
        assert result.passed_suites == 1
        assert result.failed_suites == 1

    @patch("skill_evaluator.multi_suite.load_eval_suite")
    def test_config_error_captured(self, mock_load, tmp_path):
        f1 = tmp_path / "a.eval.yaml"
        f1.touch()

        mock_load.side_effect = ConfigLoadError("bad yaml")

        result = run_suites([f1])

        assert result.total_suites == 1
        assert result.error_suites == 1
        assert result.outcomes[0].error == "bad yaml"

    @patch("skill_evaluator.multi_suite.execute_suite")
    @patch("skill_evaluator.multi_suite.load_eval_suite")
    def test_skill_parse_error_captured(self, mock_load, mock_execute, tmp_path):
        f1 = tmp_path / "a.eval.yaml"
        f1.touch()

        mock_load.return_value = _make_suite()
        mock_execute.side_effect = SkillParseError("bad skill")

        result = run_suites([f1])

        assert result.error_suites == 1
        assert "bad skill" in result.outcomes[0].error

    @patch("skill_evaluator.multi_suite.execute_suite")
    @patch("skill_evaluator.multi_suite.load_eval_suite")
    def test_filter_applied(self, mock_load, mock_execute, tmp_path):
        f1 = tmp_path / "a.eval.yaml"
        f1.touch()

        suite = _make_suite()
        mock_load.return_value = suite
        mock_execute.return_value = _make_suite_result(passed=True)

        result = run_suites([f1], cli_filter_pattern="basic")

        assert result.total_suites == 1
        assert result.outcomes[0].passed is True

    @patch("skill_evaluator.multi_suite.load_eval_suite")
    def test_filter_no_match(self, mock_load, tmp_path):
        f1 = tmp_path / "a.eval.yaml"
        f1.touch()

        mock_load.return_value = _make_suite()

        result = run_suites([f1], cli_filter_pattern="nonexistent")

        assert result.error_suites == 1
        assert "nonexistent" in result.outcomes[0].error

    @patch("skill_evaluator.multi_suite.execute_suite")
    @patch("skill_evaluator.multi_suite.load_eval_suite")
    def test_error_does_not_abort_others(self, mock_load, mock_execute, tmp_path):
        """A config error in one suite doesn't prevent the next from running."""
        f1 = tmp_path / "a.eval.yaml"
        f2 = tmp_path / "b.eval.yaml"
        f1.touch()
        f2.touch()

        mock_load.side_effect = [
            ConfigLoadError("bad"),
            _make_suite("suite-b"),
        ]
        mock_execute.return_value = _make_suite_result("suite-b", passed=True)

        result = run_suites([f1, f2])

        assert result.total_suites == 2
        assert result.error_suites == 1
        assert result.passed_suites == 1
