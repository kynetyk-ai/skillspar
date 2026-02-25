"""Tests for reporting/console.py — verbose output mode."""

from io import StringIO

from rich.console import Console

from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
from skill_evaluator.reporting.console import (
    ConsoleReporter,
    SuiteResult,
    TestResult,
    TestRunGroup,
)


def _capture_console():
    buf = StringIO()
    return Console(file=buf, no_color=True, highlight=False, width=120), buf


def _passing_result(name="test"):
    return TestResult(
        test_name=name,
        assertion_results=[
            AssertionResult(
                status=AssertionStatus.PASSED,
                assertion_type="stop_reason",
                message="ok",
            ),
            AssertionResult(
                status=AssertionStatus.PASSED,
                assertion_type="output_contains",
                message="found 'hello'",
            ),
        ],
    )


def _failing_result(name="test"):
    return TestResult(
        test_name=name,
        assertion_results=[
            AssertionResult(
                status=AssertionStatus.PASSED,
                assertion_type="stop_reason",
                message="ok",
            ),
            AssertionResult(
                status=AssertionStatus.FAILED,
                assertion_type="output_contains",
                message="Expected 'hello' not found",
            ),
        ],
    )


class TestVerboseSingleRun:
    def test_verbose_shows_all_assertions(self):
        console, buf = _capture_console()
        reporter = ConsoleReporter(console=console, verbose=True)

        suite_result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(test_name="greeting", runs=[_passing_result("greeting")]),
            ],
        )
        reporter.report(suite_result)
        output = buf.getvalue()

        # Verbose should show all assertion details, including passing ones
        assert "stop_reason" in output
        assert "output_contains" in output
        assert "PASSED" in output

    def test_non_verbose_hides_passing_details(self):
        console, buf = _capture_console()
        reporter = ConsoleReporter(console=console, verbose=False)

        suite_result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(test_name="greeting", runs=[_passing_result("greeting")]),
            ],
        )
        reporter.report(suite_result)
        output = buf.getvalue()

        # Non-verbose should NOT show individual assertion details for passing tests
        assert "stop_reason" not in output
        assert "output_contains" not in output


class TestVerboseMultiRun:
    def test_verbose_shows_per_run_breakdown(self):
        console, buf = _capture_console()
        reporter = ConsoleReporter(console=console, verbose=True)

        suite_result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(
                    test_name="multi",
                    runs=[_passing_result("multi"), _failing_result("multi")],
                    pass_threshold=0.5,
                ),
            ],
        )
        reporter.report(suite_result)
        output = buf.getvalue()

        # Should show per-run details
        assert "run 0: PASS" in output
        assert "run 1: FAIL" in output
        # Should show assertion details
        assert "stop_reason" in output
        assert "output_contains" in output

    def test_non_verbose_multi_run_unchanged(self):
        console, buf = _capture_console()
        reporter = ConsoleReporter(console=console, verbose=False)

        suite_result = SuiteResult(
            suite_name="test",
            test_results=[
                TestRunGroup(
                    test_name="multi",
                    runs=[_passing_result("multi"), _failing_result("multi")],
                    pass_threshold=0.5,
                ),
            ],
        )
        reporter.report(suite_result)
        output = buf.getvalue()

        # Non-verbose should NOT show per-run breakdown
        assert "run 0" not in output
        assert "run 1" not in output
        # But should show summary
        assert "1/2 passed" in output
