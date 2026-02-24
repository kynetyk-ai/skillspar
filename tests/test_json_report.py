"""Tests for reporting/json_report.py — JSON output."""

import json

from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
from skill_evaluator.config.schema import EvalSuite
from skill_evaluator.engine.trace import TokenUsage, ToolCall, Trace, Turn
from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup
from skill_evaluator.reporting.json_report import JsonReporter


def _make_suite(**overrides):
    raw = {
        "suite": "test suite",
        "skill": "./SKILL.md",
        "defaults": {
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": 4096,
            "runs": 1,
            "pass_threshold": 1.0,
            "concurrency": 1,
            "max_retries": 2,
        },
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


def _make_trace(text="Hello!", input_tokens=100, output_tokens=50):
    trace = Trace()
    trace.add_turn(Turn(
        text_output=text,
        tool_calls=[],
        stop_reason="end_turn",
        usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        raw_response=object(),  # non-serializable, should be excluded
    ))
    return trace


def _make_trace_with_tools():
    trace = Trace()
    trace.add_turn(Turn(
        text_output="I'll read that for you.",
        tool_calls=[
            ToolCall(id="tc_001", name="Read", input={"file_path": "/foo.py"}),
        ],
        stop_reason="tool_use",
        usage=TokenUsage(input_tokens=200, output_tokens=100),
        raw_response=None,
    ))
    return trace


def _pass_result(name="test", trace=None):
    return TestResult(
        test_name=name,
        assertion_results=[
            AssertionResult(status=AssertionStatus.PASSED, assertion_type="stop_reason", message="ok"),
        ],
        trace=trace,
    )


def _fail_result(name="test", trace=None):
    return TestResult(
        test_name=name,
        assertion_results=[
            AssertionResult(
                status=AssertionStatus.FAILED,
                assertion_type="output_contains",
                message="Output does not contain 'expected'",
                details={"expected": "expected", "actual": "Hello!"},
            ),
        ],
        trace=trace,
    )


class TestJsonReporterBuildReport:
    def test_produces_valid_structure(self):
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(
                    test_name="basic",
                    runs=[_pass_result(trace=_make_trace())],
                ),
            ],
        )
        reporter = JsonReporter()
        report = reporter.build_report(suite, suite_result)

        assert report["suite"] == "test suite"
        assert report["skill"] == "./SKILL.md"
        assert "timestamp" in report
        assert "defaults" in report
        assert "tests" in report
        assert "summary" in report

    def test_defaults_included(self):
        suite = _make_suite()
        suite_result = SuiteResult(suite_name="test suite", test_results=[])
        reporter = JsonReporter()
        report = reporter.build_report(suite, suite_result)

        defaults = report["defaults"]
        assert defaults["model"] == "claude-sonnet-4-5-20250929"
        assert defaults["runs"] == 1
        assert defaults["concurrency"] == 1
        assert defaults["max_retries"] == 2

    def test_trace_serialized_without_raw_response(self):
        trace = _make_trace()
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(test_name="t", runs=[_pass_result(trace=trace)]),
            ],
        )
        reporter = JsonReporter()
        report = reporter.build_report(suite, suite_result)

        run_data = report["tests"][0]["runs"][0]
        assert run_data["trace"] is not None
        assert run_data["trace"]["turns"][0]["text_output"] == "Hello!"
        assert "raw_response" not in run_data["trace"]["turns"][0]

    def test_tool_calls_in_trace(self):
        trace = _make_trace_with_tools()
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(test_name="t", runs=[_pass_result(trace=trace)]),
            ],
        )
        reporter = JsonReporter()
        report = reporter.build_report(suite, suite_result)

        turn = report["tests"][0]["runs"][0]["trace"]["turns"][0]
        assert len(turn["tool_calls"]) == 1
        assert turn["tool_calls"][0]["name"] == "Read"
        assert turn["usage"]["input_tokens"] == 200

    def test_assertion_results_preserved(self):
        trace = _make_trace()
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(
                    test_name="t",
                    runs=[_fail_result(trace=trace)],
                ),
            ],
        )
        reporter = JsonReporter()
        report = reporter.build_report(suite, suite_result)

        assertions = report["tests"][0]["runs"][0]["assertions"]
        assert len(assertions) == 1
        assert assertions[0]["type"] == "output_contains"
        assert assertions[0]["status"] == "failed"
        assert assertions[0]["details"]["expected"] == "expected"

    def test_baseline_runs_included(self):
        trace = _make_trace()
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(
                    test_name="t",
                    runs=[_pass_result(trace=trace)],
                    baseline_runs=[_fail_result(trace=trace)],
                ),
            ],
        )
        reporter = JsonReporter()
        report = reporter.build_report(suite, suite_result)

        test_data = report["tests"][0]
        assert "baseline_runs" in test_data
        assert len(test_data["baseline_runs"]) == 1
        assert "baseline_summary" in test_data
        assert test_data["baseline_summary"]["pass_count"] == 0

    def test_summary_computed_correctly(self):
        trace = _make_trace(input_tokens=100, output_tokens=50)
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(
                    test_name="t1",
                    runs=[_pass_result(trace=trace), _pass_result(trace=trace)],
                    pass_threshold=0.5,
                ),
                TestRunGroup(
                    test_name="t2",
                    runs=[_fail_result(trace=trace)],
                ),
            ],
        )
        reporter = JsonReporter()
        report = reporter.build_report(suite, suite_result)

        summary = report["summary"]
        assert summary["total_tests"] == 2
        assert summary["passed_tests"] == 1
        assert summary["failed_tests"] == 1
        assert summary["all_passed"] is False
        assert summary["total_api_calls"] == 3
        assert summary["total_tokens"]["input_tokens"] == 300
        assert summary["total_tokens"]["output_tokens"] == 150

    def test_no_trace_results_in_null(self):
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(test_name="t", runs=[_pass_result(trace=None)]),
            ],
        )
        reporter = JsonReporter()
        report = reporter.build_report(suite, suite_result)

        assert report["tests"][0]["runs"][0]["trace"] is None


class TestJsonReporterWrite:
    def test_write_produces_valid_json(self, tmp_path):
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(
                    test_name="t",
                    runs=[_pass_result(trace=_make_trace())],
                ),
            ],
        )
        reporter = JsonReporter()
        report = reporter.build_report(suite, suite_result)

        out_path = tmp_path / "results.json"
        reporter.write(report, out_path)

        assert out_path.exists()
        with open(out_path) as f:
            data = json.load(f)
        assert data["suite"] == "test suite"

    def test_write_creates_parent_dirs(self, tmp_path):
        suite = _make_suite()
        suite_result = SuiteResult(suite_name="test", test_results=[])
        reporter = JsonReporter()
        report = reporter.build_report(suite, suite_result)

        out_path = tmp_path / "nested" / "dir" / "results.json"
        reporter.write(report, out_path)
        assert out_path.exists()
