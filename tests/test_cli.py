"""Tests for cli.py — Click CliRunner."""

import json
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from skill_evaluator.cli import main


def _make_passing_suite_result():
    from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
    from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup

    return SuiteResult(
        suite_name="test",
        test_results=[
            TestRunGroup(
                test_name="t1",
                runs=[
                    TestResult(
                        test_name="t1",
                        assertion_results=[
                            AssertionResult(
                                status=AssertionStatus.PASSED,
                                assertion_type="stop_reason",
                                message="ok",
                            )
                        ],
                    )
                ],
            )
        ],
    )


def _make_mock_suite(*, real_values=False):
    from skill_evaluator.config.schema import SuiteDefaults

    mock_suite = MagicMock()
    mock_suite.defaults = SuiteDefaults()
    if real_values:
        mock_suite.suite = "test"
        mock_suite.skill = "./SKILL.md"
    return mock_suite


class TestCli:
    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_run_missing_file(self):
        runner = CliRunner()
        result = runner.invoke(main, ["run", "nonexistent.yaml"])
        assert result.exit_code != 0

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_run_success(self, mock_load, mock_runner_cls, tmp_path):
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        mock_load.return_value = _make_mock_suite()
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.run.return_value = _make_passing_suite_result()

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file)])
        assert result.exit_code == 0

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_run_failure_exit_code(self, mock_load, mock_runner_cls, tmp_path):
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        mock_load.return_value = _make_mock_suite()
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
        from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup

        mock_runner.run.return_value = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(
                    test_name="t1",
                    runs=[
                        TestResult(
                            test_name="t1",
                            assertion_results=[
                                AssertionResult(
                                    status=AssertionStatus.FAILED,
                                    assertion_type="stop_reason",
                                    message="bad",
                                )
                            ],
                        )
                    ],
                )
            ],
        )

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file)])
        assert result.exit_code == 1

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_runs_flag_applied(self, mock_load, mock_runner_cls, tmp_path):
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        mock_suite = _make_mock_suite()
        mock_load.return_value = mock_suite
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.run.return_value = _make_passing_suite_result()

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file), "--runs", "5"])
        assert result.exit_code == 0
        assert mock_suite.defaults.runs == 5

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_concurrency_flag_applied(self, mock_load, mock_runner_cls, tmp_path):
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        mock_suite = _make_mock_suite()
        mock_load.return_value = mock_suite
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.run.return_value = _make_passing_suite_result()

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file), "--concurrency", "4"])
        assert result.exit_code == 0
        assert mock_suite.defaults.concurrency == 4

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_output_as_file_path(self, mock_load, mock_runner_cls, tmp_path):
        """--output with .json extension is treated as file path directly."""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")
        output_file = tmp_path / "results.json"

        mock_suite = _make_mock_suite(real_values=True)
        mock_load.return_value = mock_suite
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.run.return_value = _make_passing_suite_result()

        runner = CliRunner()
        result = runner.invoke(
            main, ["run", str(eval_file), "--output", str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        with open(output_file) as f:
            data = json.load(f)
        assert data["suite"] == "test"
        assert "JSON report written" in result.output

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_format_flag_junit(self, mock_load, mock_runner_cls, tmp_path):
        """--format junit produces XML file."""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")
        output_file = tmp_path / "results.xml"

        mock_suite = _make_mock_suite(real_values=True)
        mock_load.return_value = mock_suite
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.run.return_value = _make_passing_suite_result()

        runner = CliRunner()
        result = runner.invoke(
            main, ["run", str(eval_file), "--format", "junit", "--output", str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        parsed = ET.parse(output_file)
        assert parsed.getroot().tag == "testsuites"
        assert "JUnit report written" in result.output

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_format_inferred_from_extension(self, mock_load, mock_runner_cls, tmp_path):
        """--output with .xml extension triggers junit format."""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")
        output_file = tmp_path / "results.xml"

        mock_suite = _make_mock_suite(real_values=True)
        mock_load.return_value = mock_suite
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.run.return_value = _make_passing_suite_result()

        runner = CliRunner()
        result = runner.invoke(
            main, ["run", str(eval_file), "--output", str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        parsed = ET.parse(output_file)
        assert parsed.getroot().tag == "testsuites"

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_filter_flag(self, mock_load, mock_runner_cls, tmp_path):
        """--filter only runs matching tests."""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        from skill_evaluator.config.schema import (
            InputConfig,
            MessageConfig,
            SingleTurnTest,
            StopReasonAssertion,
        )

        mock_suite = _make_mock_suite()
        mock_suite.tests = [
            SingleTurnTest(
                type="single_turn",
                name="greeting test",
                input=InputConfig(messages=[MessageConfig(role="user", content="hi")]),
                assertions=[StopReasonAssertion(type="stop_reason", value="end_turn")],
            ),
            SingleTurnTest(
                type="single_turn",
                name="farewell test",
                input=InputConfig(messages=[MessageConfig(role="user", content="bye")]),
                assertions=[StopReasonAssertion(type="stop_reason", value="end_turn")],
            ),
        ]
        mock_load.return_value = mock_suite
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.run.return_value = _make_passing_suite_result()

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file), "--filter", "greeting"])
        assert result.exit_code == 0
        # Only "greeting test" should remain
        assert len(mock_suite.tests) == 1
        assert mock_suite.tests[0].name == "greeting test"

    @patch("skill_evaluator.cli.load_eval_suite")
    def test_filter_no_match_exits(self, mock_load, tmp_path):
        """--filter with no matching tests exits with error."""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        from skill_evaluator.config.schema import (
            InputConfig,
            MessageConfig,
            SingleTurnTest,
            StopReasonAssertion,
        )

        mock_suite = _make_mock_suite()
        mock_suite.tests = [
            SingleTurnTest(
                type="single_turn",
                name="greeting test",
                input=InputConfig(messages=[MessageConfig(role="user", content="hi")]),
                assertions=[StopReasonAssertion(type="stop_reason", value="end_turn")],
            ),
        ]
        mock_load.return_value = mock_suite

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file), "--filter", "nonexistent"])
        assert result.exit_code == 1
        assert "no tests match" in result.output

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_model_override(self, mock_load, mock_runner_cls, tmp_path):
        """--model overrides suite default model."""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        mock_suite = _make_mock_suite()
        mock_load.return_value = mock_suite
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.run.return_value = _make_passing_suite_result()

        runner = CliRunner()
        result = runner.invoke(
            main, ["run", str(eval_file), "--model", "claude-opus-4"]
        )
        assert result.exit_code == 0
        assert mock_suite.defaults.model == "claude-opus-4"

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_verbose_flag(self, mock_load, mock_runner_cls, tmp_path):
        """--verbose is passed to ConsoleReporter."""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        mock_load.return_value = _make_mock_suite()
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.run.return_value = _make_passing_suite_result()

        runner = CliRunner()
        with patch("skill_evaluator.cli.ConsoleReporter") as mock_reporter_cls:
            mock_reporter_cls.return_value = MagicMock()
            result = runner.invoke(main, ["run", str(eval_file), "--verbose"])
            assert result.exit_code == 0
            mock_reporter_cls.assert_called_once_with(verbose=True)

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_log_level_flag(self, mock_load, mock_runner_cls, tmp_path):
        """--log-level is accepted without error."""
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        mock_load.return_value = _make_mock_suite()
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.run.return_value = _make_passing_suite_result()

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file), "--log-level", "DEBUG"])
        assert result.exit_code == 0
