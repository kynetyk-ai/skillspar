"""Tests for reporting/console.py — Rich output."""

from io import StringIO

import pytest
from rich.console import Console

from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
from skill_evaluator.reporting.console import (
    ConsoleReporter,
    SuiteResult,
    TestResult,
    TestRunGroup,
)


# ---------------------------------------------------------------------------
# TestResult (unchanged behaviour)
# ---------------------------------------------------------------------------


class TestTestResult:
    def test_all_passed(self):
        tr = TestResult(
            test_name="test",
            assertion_results=[
                AssertionResult(
                    status=AssertionStatus.PASSED, assertion_type="stop_reason", message="ok"
                ),
            ],
        )
        assert tr.passed is True
        assert tr.status_label == "PASS"

    def test_failure(self):
        tr = TestResult(
            test_name="test",
            assertion_results=[
                AssertionResult(
                    status=AssertionStatus.FAILED, assertion_type="stop_reason", message="bad"
                ),
            ],
        )
        assert tr.passed is False
        assert tr.status_label == "FAIL"

    def test_skipped_counts_as_pass(self):
        tr = TestResult(
            test_name="test",
            assertion_results=[
                AssertionResult(
                    status=AssertionStatus.SKIPPED, assertion_type="llm_judge", message="skipped"
                ),
            ],
        )
        assert tr.passed is True

    def test_empty_results_skip(self):
        tr = TestResult(test_name="test")
        assert tr.status_label == "SKIP"


# ---------------------------------------------------------------------------
# TestRunGroup
# ---------------------------------------------------------------------------

def _pass_result(name="test"):
    return TestResult(
        test_name=name,
        assertion_results=[
            AssertionResult(status=AssertionStatus.PASSED, assertion_type="x", message="ok"),
        ],
    )


def _fail_result(name="test"):
    return TestResult(
        test_name=name,
        assertion_results=[
            AssertionResult(status=AssertionStatus.FAILED, assertion_type="x", message="bad"),
        ],
    )


class TestTestRunGroup:
    def test_single_run_backward_compat(self):
        group = TestRunGroup(test_name="t1", runs=[_pass_result()])
        assert group.pass_count == 1
        assert group.pass_rate == 1.0
        assert group.passed is True
        assert group.is_multi_run is False
        assert group.status_label == "PASS"

    def test_single_run_failure(self):
        group = TestRunGroup(test_name="t1", runs=[_fail_result()])
        assert group.passed is False
        assert group.status_label == "FAIL"

    def test_multi_run_pass_rate(self):
        runs = [_pass_result(), _pass_result(), _fail_result(), _pass_result()]
        group = TestRunGroup(test_name="t1", runs=runs, pass_threshold=0.75)
        assert group.pass_count == 3
        assert group.pass_rate == 0.75
        assert group.passed is True
        assert group.is_multi_run is True

    def test_multi_run_below_threshold(self):
        runs = [_pass_result(), _fail_result(), _fail_result()]
        group = TestRunGroup(test_name="t1", runs=runs, pass_threshold=0.8)
        assert group.pass_rate == pytest.approx(1 / 3)
        assert group.passed is False

    def test_multi_run_exact_threshold(self):
        runs = [_pass_result(), _pass_result(), _pass_result(), _pass_result(), _fail_result()]
        group = TestRunGroup(test_name="t1", runs=runs, pass_threshold=0.8)
        assert group.pass_rate == 0.8
        assert group.passed is True

    def test_baseline_pass_count(self):
        group = TestRunGroup(
            test_name="t1",
            runs=[_pass_result()],
            baseline_runs=[_pass_result(), _fail_result(), _pass_result()],
        )
        assert group.baseline_pass_count == 2

    def test_no_baseline_returns_zero(self):
        group = TestRunGroup(test_name="t1", runs=[_pass_result()])
        assert group.baseline_pass_count == 0

    def test_status_label_multi_run(self):
        group = TestRunGroup(
            test_name="t1",
            runs=[_pass_result(), _pass_result()],
            pass_threshold=1.0,
        )
        assert group.status_label == "PASS"


# ---------------------------------------------------------------------------
# SuiteResult with TestRunGroup
# ---------------------------------------------------------------------------


class TestSuiteResult:
    def test_all_passed(self):
        sr = SuiteResult(
            suite_name="suite",
            test_results=[
                TestRunGroup(test_name="t1", runs=[_pass_result()]),
            ],
        )
        assert sr.all_passed is True
        assert sr.passed_count == 1
        assert sr.failed_count == 0

    def test_with_failure(self):
        sr = SuiteResult(
            suite_name="suite",
            test_results=[
                TestRunGroup(test_name="t1", runs=[_pass_result()]),
                TestRunGroup(test_name="t2", runs=[_fail_result()]),
            ],
        )
        assert sr.all_passed is False
        assert sr.passed_count == 1
        assert sr.failed_count == 1

    def test_multi_run_group_pass(self):
        sr = SuiteResult(
            suite_name="suite",
            test_results=[
                TestRunGroup(
                    test_name="t1",
                    runs=[_pass_result(), _pass_result(), _fail_result()],
                    pass_threshold=0.6,
                ),
            ],
        )
        assert sr.all_passed is True


# ---------------------------------------------------------------------------
# ConsoleReporter
# ---------------------------------------------------------------------------


class TestConsoleReporter:
    def test_report_all_passed(self):
        output = StringIO()
        console = Console(file=output, no_color=True, width=120)
        reporter = ConsoleReporter(console=console)

        suite_result = SuiteResult(
            suite_name="my suite",
            test_results=[
                TestRunGroup(
                    test_name="test one",
                    runs=[_pass_result("test one")],
                ),
            ],
        )
        reporter.report(suite_result)
        text = output.getvalue()
        assert "my suite" in text
        assert "test one" in text
        assert "1/1 tests passed" in text

    def test_report_with_failure(self):
        output = StringIO()
        console = Console(file=output, no_color=True, width=120)
        reporter = ConsoleReporter(console=console)

        suite_result = SuiteResult(
            suite_name="suite",
            test_results=[
                TestRunGroup(
                    test_name="failing test",
                    runs=[_fail_result("failing test")],
                ),
            ],
        )
        reporter.report(suite_result)
        text = output.getvalue()
        assert "failing test" in text
        assert "1/1 tests failed" in text

    def test_multi_run_display(self):
        output = StringIO()
        console = Console(file=output, no_color=True, width=120)
        reporter = ConsoleReporter(console=console)

        suite_result = SuiteResult(
            suite_name="suite",
            test_results=[
                TestRunGroup(
                    test_name="multi run test",
                    runs=[_pass_result(), _pass_result(), _fail_result()],
                    pass_threshold=0.6,
                ),
            ],
        )
        reporter.report(suite_result)
        text = output.getvalue()
        assert "2/3 passed" in text

    def test_multi_run_failure_shows_threshold(self):
        output = StringIO()
        console = Console(file=output, no_color=True, width=120)
        reporter = ConsoleReporter(console=console)

        suite_result = SuiteResult(
            suite_name="suite",
            test_results=[
                TestRunGroup(
                    test_name="below threshold",
                    runs=[_pass_result(), _fail_result(), _fail_result()],
                    pass_threshold=0.8,
                ),
            ],
        )
        reporter.report(suite_result)
        text = output.getvalue()
        assert "1/3 passed" in text
        assert "threshold: 80%" in text

    def test_baseline_display(self):
        output = StringIO()
        console = Console(file=output, no_color=True, width=120)
        reporter = ConsoleReporter(console=console)

        suite_result = SuiteResult(
            suite_name="suite",
            test_results=[
                TestRunGroup(
                    test_name="baseline test",
                    runs=[_pass_result(), _pass_result()],
                    baseline_runs=[_pass_result(), _fail_result()],
                    pass_threshold=0.5,
                ),
            ],
        )
        reporter.report(suite_result)
        text = output.getvalue()
        assert "baseline: 1/2 passed" in text
