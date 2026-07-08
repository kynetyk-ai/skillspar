"""Tests for Phase 4C features: duration, metadata, cache reporting, exit codes."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
from skill_evaluator.cli import main
from skill_evaluator.config.schema import EvalSuite
from skill_evaluator.engine.trace import TokenUsage, Trace, Turn
from skill_evaluator.reporting.console import (
    ConsoleReporter,
    SuiteResult,
    TestResult,
    TestRunGroup,
)
from skill_evaluator.reporting.json_report import JsonReporter
from skill_evaluator.reporting.junit import JunitReporter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trace(input_tokens=100, output_tokens=50, cache_creation=None, cache_read=None):
    trace = Trace()
    trace.add_turn(
        Turn(
            text_output="Hello!",
            tool_calls=[],
            stop_reason="end_turn",
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_input_tokens=cache_creation,
                cache_read_input_tokens=cache_read,
            ),
            raw_response=None,
        )
    )
    return trace


def _pass_result(name="test", trace=None, duration=None):
    return TestResult(
        test_name=name,
        assertion_results=[
            AssertionResult(
                status=AssertionStatus.PASSED, assertion_type="stop_reason", message="ok"
            ),
        ],
        trace=trace,
        duration_seconds=duration,
    )


def _make_suite(**overrides):
    raw = {
        "suite": "test suite",
        "skill": "./SKILL.md",
        "defaults": {"model": "claude-sonnet-4-5-20250929"},
        "tests": [
            {
                "type": "single_turn",
                "name": "basic",
                "input": {"messages": [{"role": "user", "content": "Hi"}]},
                "assertions": [{"type": "stop_reason", "value": "end_turn"}],
            }
        ],
    }
    raw.update(overrides)
    return EvalSuite.model_validate(raw)


# ---------------------------------------------------------------------------
# Duration tracking
# ---------------------------------------------------------------------------


class TestDurationTracking:
    def test_test_result_duration_in_dict(self):
        tr = _pass_result(duration=1.234)
        d = tr.to_dict()
        assert d["duration_seconds"] == 1.234

    def test_test_result_no_duration(self):
        tr = _pass_result()
        d = tr.to_dict()
        assert "duration_seconds" not in d

    def test_group_duration_sums_runs(self):
        group = TestRunGroup(
            test_name="t",
            runs=[_pass_result(duration=1.0), _pass_result(duration=2.0)],
        )
        assert group.duration_seconds == 3.0

    def test_group_duration_includes_baseline(self):
        group = TestRunGroup(
            test_name="t",
            runs=[_pass_result(duration=1.0)],
            baseline_runs=[_pass_result(duration=0.5)],
        )
        assert group.duration_seconds == 1.5

    def test_group_duration_none_when_no_timing(self):
        group = TestRunGroup(test_name="t", runs=[_pass_result()])
        assert group.duration_seconds is None

    def test_group_to_dict_includes_duration(self):
        group = TestRunGroup(
            test_name="t",
            runs=[_pass_result(duration=1.5)],
        )
        d = group.to_dict()
        assert d["summary"]["duration_seconds"] == 1.5


class TestJunitDuration:
    def test_time_attribute_on_testcase(self):
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(
                    test_name="t",
                    runs=[_pass_result(duration=2.5)],
                ),
            ],
        )
        reporter = JunitReporter()
        root = reporter.build_report(suite, suite_result)
        tc = root.find(".//testcase")
        assert tc is not None
        assert tc.get("time") == "2.500"

    def test_time_attribute_on_testsuite(self):
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(
                    test_name="t",
                    runs=[_pass_result(duration=1.0), _pass_result(duration=2.0)],
                ),
            ],
        )
        reporter = JunitReporter()
        root = reporter.build_report(suite, suite_result)
        ts = root.find(".//testsuite")
        assert ts is not None
        assert ts.get("time") == "3.000"

    def test_no_time_when_no_duration(self):
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(test_name="t", runs=[_pass_result()]),
            ],
        )
        reporter = JunitReporter()
        root = reporter.build_report(suite, suite_result)
        tc = root.find(".//testcase")
        assert tc.get("time") is None


# ---------------------------------------------------------------------------
# JSON report metadata
# ---------------------------------------------------------------------------


class TestJsonReportMetadata:
    def test_schema_version(self):
        suite = _make_suite()
        result = SuiteResult(suite_name="test", test_results=[])
        report = JsonReporter().build_report(suite, result)
        assert report["schema_version"] == "1"

    def test_run_id_included(self):
        suite = _make_suite()
        result = SuiteResult(suite_name="test", test_results=[], run_id="abc-123")
        report = JsonReporter().build_report(suite, result)
        assert report["run_id"] == "abc-123"

    def test_skill_file_hash_included(self):
        suite = _make_suite()
        result = SuiteResult(suite_name="test", test_results=[], skill_file_hash="deadbeef")
        report = JsonReporter().build_report(suite, result)
        assert report["skill_file_hash"] == "deadbeef"

    def test_judge_model_in_defaults(self):
        suite = _make_suite(
            defaults={
                "model": "claude-sonnet-4-5-20250929",
                "judge_model": "claude-opus-4-20250514",
            }
        )
        result = SuiteResult(suite_name="test", test_results=[])
        report = JsonReporter().build_report(suite, result)
        assert report["defaults"]["judge_model"] == "claude-opus-4-20250514"

    def test_system_prompt_in_defaults(self):
        suite = _make_suite(
            defaults={
                "model": "claude-sonnet-4-5-20250929",
                "system_prompt": "You are helpful.",
            }
        )
        result = SuiteResult(suite_name="test", test_results=[])
        report = JsonReporter().build_report(suite, result)
        assert report["defaults"]["system_prompt"] == "You are helpful."

    def test_total_duration_in_summary(self):
        suite = _make_suite()
        trace = _make_trace()
        result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(
                    test_name="t",
                    runs=[_pass_result(trace=trace, duration=1.5)],
                ),
            ],
        )
        report = JsonReporter().build_report(suite, result)
        assert report["summary"]["total_duration_seconds"] == 1.5


# ---------------------------------------------------------------------------
# Cache reporting in JSON
# ---------------------------------------------------------------------------


class TestJsonCacheReporting:
    def test_cache_summary_present(self):
        suite = _make_suite()
        trace = _make_trace(cache_creation=1000, cache_read=5000)
        result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(
                    test_name="t",
                    runs=[_pass_result(trace=trace)],
                ),
            ],
        )
        report = JsonReporter().build_report(suite, result)
        cs = report["summary"]["cache_summary"]
        assert cs["cache_creation_input_tokens"] == 1000
        assert cs["cache_read_input_tokens"] == 5000

    def test_no_cache_summary_without_cache_data(self):
        suite = _make_suite()
        trace = _make_trace()
        result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(
                    test_name="t",
                    runs=[_pass_result(trace=trace)],
                ),
            ],
        )
        report = JsonReporter().build_report(suite, result)
        assert "cache_summary" not in report["summary"]


# ---------------------------------------------------------------------------
# Per-run cost in JSON report
# ---------------------------------------------------------------------------


class TestJsonPerRunCost:
    def test_cost_usd_injected(self):
        suite = _make_suite()
        trace = _make_trace(input_tokens=1000, output_tokens=500)
        result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(
                    test_name="t",
                    runs=[_pass_result(trace=trace)],
                ),
            ],
        )
        report = JsonReporter().build_report(suite, result, model="claude-sonnet-4-5-20250929")
        run_data = report["tests"][0]["runs"][0]
        assert "cost_usd" in run_data
        assert run_data["cost_usd"] > 0

    def test_no_cost_without_model(self):
        suite = _make_suite()
        trace = _make_trace()
        result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(
                    test_name="t",
                    runs=[_pass_result(trace=trace)],
                ),
            ],
        )
        report = JsonReporter().build_report(suite, result)
        run_data = report["tests"][0]["runs"][0]
        assert "cost_usd" not in run_data


# ---------------------------------------------------------------------------
# Console reporter cost/cache display
# ---------------------------------------------------------------------------


class TestConsoleReporterCostCache:
    def test_verbose_shows_cost(self):
        from io import StringIO

        from rich.console import Console

        output = StringIO()
        console = Console(file=output, no_color=True, width=120)
        reporter = ConsoleReporter(console=console, verbose=True)

        suite_result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(test_name="t", runs=[_pass_result()]),
            ],
        )
        cost = {"total_cost_usd": 0.14, "skill_cost_usd": 0.09, "baseline_cost_usd": 0.05}
        reporter.report(suite_result, cost_summary=cost)
        text = output.getvalue()
        assert "Cost: $0.14" in text
        assert "skill: $0.09" in text
        assert "baseline: $0.05" in text

    def test_verbose_shows_cache(self):
        from io import StringIO

        from rich.console import Console

        output = StringIO()
        console = Console(file=output, no_color=True, width=120)
        reporter = ConsoleReporter(console=console, verbose=True)

        suite_result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(test_name="t", runs=[_pass_result()]),
            ],
        )
        cache = {
            "cache_creation_input_tokens": 3200,
            "cache_read_input_tokens": 12450,
            "estimated_savings_usd": 0.02,
        }
        reporter.report(suite_result, cache_summary=cache)
        text = output.getvalue()
        assert "12,450 reads" in text
        assert "3,200 writes" in text
        assert "$0.02 saved" in text

    def test_non_verbose_hides_cost_cache(self):
        from io import StringIO

        from rich.console import Console

        output = StringIO()
        console = Console(file=output, no_color=True, width=120)
        reporter = ConsoleReporter(console=console, verbose=False)

        suite_result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(test_name="t", runs=[_pass_result()]),
            ],
        )
        cost = {"total_cost_usd": 0.14, "skill_cost_usd": 0.09}
        cache = {"cache_creation_input_tokens": 100, "cache_read_input_tokens": 200}
        reporter.report(suite_result, cost_summary=cost, cache_summary=cache)
        text = output.getvalue()
        assert "Cost" not in text
        assert "Cache" not in text


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


class TestExitCodes:
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_config_load_error_exits_2(self, mock_load, tmp_path):
        from skill_evaluator.config.loader import ConfigLoadError

        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")
        mock_load.side_effect = ConfigLoadError("bad config")

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file)])
        assert result.exit_code == 2

    @patch("skill_evaluator.cli.execute_suite")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_skill_parse_error_exits_2(self, mock_load, mock_execute, tmp_path):
        from skill_evaluator.config.schema import SuiteDefaults
        from skill_evaluator.skill.parser import SkillParseError

        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        mock_suite = MagicMock()
        mock_suite.defaults = SuiteDefaults()
        mock_load.return_value = mock_suite
        mock_execute.side_effect = SkillParseError("bad skill")

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file)])
        assert result.exit_code == 2
        assert "bad skill" in result.output

    @patch("skill_evaluator.cli.execute_suite")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_prefix_load_error_exits_2(self, mock_load, mock_execute, tmp_path):
        from skill_evaluator.config.schema import SuiteDefaults
        from skill_evaluator.engine.prefix import PrefixLoadError

        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        mock_suite = MagicMock()
        mock_suite.defaults = SuiteDefaults()
        mock_load.return_value = mock_suite
        mock_execute.side_effect = PrefixLoadError("bad prefix")

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file)])
        assert result.exit_code == 2
        assert "bad prefix" in result.output

    @patch("skill_evaluator.cli.execute_suite")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_test_failure_exits_1(self, mock_load, mock_execute, tmp_path):
        from skill_evaluator.config.schema import SuiteDefaults

        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        mock_suite = MagicMock()
        mock_suite.defaults = SuiteDefaults()
        mock_load.return_value = mock_suite
        mock_execute.return_value = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(
                    test_name="t",
                    runs=[
                        TestResult(
                            test_name="t",
                            assertion_results=[
                                AssertionResult(
                                    status=AssertionStatus.FAILED,
                                    assertion_type="x",
                                    message="fail",
                                ),
                            ],
                        )
                    ],
                ),
            ],
        )

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file)])
        assert result.exit_code == 1

    @patch("skill_evaluator.cli.execute_suite")
    @patch("skill_evaluator.cli.load_eval_suite")
    def test_all_pass_exits_0(self, mock_load, mock_execute, tmp_path):
        from skill_evaluator.config.schema import SuiteDefaults

        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        mock_suite = MagicMock()
        mock_suite.defaults = SuiteDefaults()
        mock_load.return_value = mock_suite
        mock_execute.return_value = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(test_name="t", runs=[_pass_result()]),
            ],
        )

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(eval_file)])
        assert result.exit_code == 0

    def test_snapshot_save_missing_api_key_exits_2(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        eval_file = tmp_path / "test.eval.yaml"
        eval_file.write_text("placeholder")

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["snapshot", "save", str(eval_file)])
        assert result.exit_code == 2
        assert "ANTHROPIC_API_KEY" in result.output
