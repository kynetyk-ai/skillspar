"""Tests for cli.py — Click CliRunner."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from skill_evaluator.cli import main


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

        mock_suite = MagicMock()
        mock_suite.defaults = MagicMock()
        mock_load.return_value = mock_suite

        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup
        from skill_evaluator.assertions.base import AssertionResult, AssertionStatus

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

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file)])
        assert result.exit_code == 0

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_run_failure_exit_code(self, mock_load, mock_runner_cls, tmp_path):
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        mock_suite = MagicMock()
        mock_suite.defaults = MagicMock()
        mock_load.return_value = mock_suite

        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup
        from skill_evaluator.assertions.base import AssertionResult, AssertionStatus

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

        mock_suite = MagicMock()
        mock_suite.defaults = MagicMock()
        mock_suite.defaults.runs = 1
        mock_suite.defaults.concurrency = 1
        mock_load.return_value = mock_suite

        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup
        from skill_evaluator.assertions.base import AssertionResult, AssertionStatus

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

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file), "--runs", "5"])
        assert result.exit_code == 0
        assert mock_suite.defaults.runs == 5

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_concurrency_flag_applied(self, mock_load, mock_runner_cls, tmp_path):
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        mock_suite = MagicMock()
        mock_suite.defaults = MagicMock()
        mock_suite.defaults.runs = 1
        mock_suite.defaults.concurrency = 1
        mock_load.return_value = mock_suite

        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup
        from skill_evaluator.assertions.base import AssertionResult, AssertionStatus

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

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file), "--concurrency", "4"])
        assert result.exit_code == 0
        assert mock_suite.defaults.concurrency == 4

    @patch("skill_evaluator.cli.SuiteRunner")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_output_flag_writes_json(self, mock_load, mock_runner_cls, tmp_path):
        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")
        output_file = tmp_path / "results.json"

        mock_suite = MagicMock()
        mock_suite.defaults = MagicMock()
        mock_suite.defaults.runs = 1
        mock_suite.defaults.concurrency = 1
        # Provide real values for JsonReporter.build_report
        mock_suite.suite = "test"
        mock_suite.skill = "./SKILL.md"
        mock_suite.defaults.model = "claude-sonnet-4-5-20250929"
        mock_suite.defaults.max_tokens = 4096
        mock_suite.defaults.temperature = 0
        mock_suite.defaults.pass_threshold = 1.0
        mock_suite.defaults.max_retries = 2
        mock_load.return_value = mock_suite

        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup
        from skill_evaluator.assertions.base import AssertionResult, AssertionStatus

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
