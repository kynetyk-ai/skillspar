"""Tests for multi-suite reporting."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path

from rich.console import Console

from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
from skill_evaluator.config.schema import (
    EvalSuite,
    InputConfig,
    MessageConfig,
    OutputContainsAssertion,
    SingleTurnTest,
    SuiteDefaults,
)
from skill_evaluator.multi_suite import MultiSuiteResult, SuiteOutcome
from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup
from skill_evaluator.reporting.multi_suite_report import (
    build_multi_suite_json_report,
    build_multi_suite_junit_report,
    display_multi_suite_summary,
)


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


def _make_suite_result(name="test-suite", passed=True, num_tests=1):
    status = AssertionStatus.PASSED if passed else AssertionStatus.FAILED
    results = []
    for i in range(num_tests):
        results.append(
            TestRunGroup(
                test_name=f"test-{i}",
                runs=[
                    TestResult(
                        test_name=f"test-{i}",
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
        )
    return SuiteResult(suite_name=name, test_results=results)


def _make_config():
    from skill_evaluator.config.schema import ResolvedConfig

    return ResolvedConfig()


def _make_outcome(name="test-suite", passed=True, num_tests=1, error=None, cost=None):
    if error:
        return SuiteOutcome(eval_file=Path(f"{name}.eval.yaml"), error=error)
    return SuiteOutcome(
        eval_file=Path(f"{name}.eval.yaml"),
        suite=_make_suite(name),
        suite_result=_make_suite_result(name, passed=passed, num_tests=num_tests),
        config=_make_config(),
        cost_summary={"total_cost_usd": cost} if cost else None,
    )


class TestDisplayMultiSuiteSummary:
    def _capture(self, result, verbose=False):
        buf = StringIO()
        console = Console(file=buf, no_color=True, width=120)
        display_multi_suite_summary(result, console, verbose=verbose)
        return buf.getvalue()

    def test_all_passing(self):
        result = MultiSuiteResult(
            outcomes=[
                _make_outcome("suite-a", passed=True, num_tests=3),
                _make_outcome("suite-b", passed=True, num_tests=2),
            ]
        )
        output = self._capture(result)
        assert "Multi-Suite Summary" in output
        assert "suite-a" in output
        assert "suite-b" in output
        assert "PASS" in output
        assert "2 suites" in output
        assert "2 passed" in output

    def test_one_failing(self):
        result = MultiSuiteResult(
            outcomes=[
                _make_outcome("suite-a", passed=True, num_tests=3),
                _make_outcome("suite-b", passed=False, num_tests=2),
            ]
        )
        output = self._capture(result)
        assert "FAIL" in output
        assert "1 failed" in output
        assert "1 passed" in output

    def test_error_suite(self):
        result = MultiSuiteResult(
            outcomes=[
                _make_outcome("suite-a", passed=True),
                _make_outcome("bad-suite", error="config error"),
            ]
        )
        output = self._capture(result)
        assert "ERROR" in output
        assert "1 errored" in output

    def test_cost_displayed(self):
        result = MultiSuiteResult(
            outcomes=[
                _make_outcome("suite-a", passed=True, cost=0.50),
                _make_outcome("suite-b", passed=True, cost=0.75),
            ]
        )
        output = self._capture(result)
        assert "$0.50" in output
        assert "$0.75" in output
        assert "$1.25" in output  # total

    def test_tests_column_shows_counts(self):
        result = MultiSuiteResult(
            outcomes=[
                _make_outcome("suite-a", passed=True, num_tests=4),
            ]
        )
        output = self._capture(result)
        assert "4/4" in output


class TestBuildMultiSuiteJsonReport:
    def test_basic_structure(self):
        result = MultiSuiteResult(
            outcomes=[
                _make_outcome("suite-a", passed=True),
                _make_outcome("suite-b", passed=False),
            ]
        )
        report = build_multi_suite_json_report(result)

        assert report["schema_version"] == "1"
        assert report["type"] == "multi_suite"
        assert "timestamp" in report
        assert len(report["suites"]) == 2
        assert report["summary"]["total_suites"] == 2
        assert report["summary"]["passed_suites"] == 1
        assert report["summary"]["failed_suites"] == 1
        assert report["summary"]["all_passed"] is False

    def test_error_suite_in_report(self):
        result = MultiSuiteResult(
            outcomes=[
                _make_outcome("bad-suite", error="config error"),
            ]
        )
        report = build_multi_suite_json_report(result)

        assert len(report["suites"]) == 1
        suite_entry = report["suites"][0]
        assert suite_entry["error"] == "config error"
        assert report["summary"]["error_suites"] == 1

    def test_passing_suite_has_full_report(self):
        result = MultiSuiteResult(
            outcomes=[
                _make_outcome("suite-a", passed=True),
            ]
        )
        report = build_multi_suite_json_report(result)

        suite_entry = report["suites"][0]
        assert "suite" in suite_entry
        assert "tests" in suite_entry
        assert "summary" in suite_entry
        assert suite_entry["eval_file"] == "suite-a.eval.yaml"

    def test_cost_in_summary(self):
        result = MultiSuiteResult(
            outcomes=[
                _make_outcome("suite-a", passed=True, cost=1.5),
            ]
        )
        report = build_multi_suite_json_report(result)
        assert report["summary"]["total_cost_usd"] == 1.5


class TestBuildMultiSuiteJunitReport:
    def test_valid_xml(self):
        result = MultiSuiteResult(
            outcomes=[
                _make_outcome("suite-a", passed=True, num_tests=2),
                _make_outcome("suite-b", passed=False, num_tests=1),
            ]
        )
        root = build_multi_suite_junit_report(result)

        assert root.tag == "testsuites"
        # Each suite produces testsuite children
        testsuites = root.findall("testsuite")
        assert len(testsuites) >= 2

    def test_error_suite_in_junit(self):
        result = MultiSuiteResult(
            outcomes=[
                _make_outcome("bad-suite", error="config error"),
            ]
        )
        root = build_multi_suite_junit_report(result)

        testsuites = root.findall("testsuite")
        assert len(testsuites) == 1
        ts = testsuites[0]
        assert ts.get("name") == "bad-suite.eval"  # falls back to file stem
        assert ts.get("errors") == "1"
        # Should have an error element
        tc = ts.find("testcase")
        assert tc is not None
        err = tc.find("error")
        assert err is not None
        assert "config error" in err.get("message", "")

    def test_xml_serializable(self):
        """Verify the report can be serialized to XML string."""
        result = MultiSuiteResult(
            outcomes=[
                _make_outcome("suite-a", passed=True),
            ]
        )
        root = build_multi_suite_junit_report(result)
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        # Should not raise
        xml_str = ET.tostring(root, encoding="unicode")
        assert "<testsuites>" in xml_str
