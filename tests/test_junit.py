"""Tests for reporting/junit.py — JUnit XML reporter."""

import xml.etree.ElementTree as ET

from skill_evaluator.assertions.base import AssertionResult, AssertionStatus
from skill_evaluator.config.schema import EvalSuite, SuiteDefaults
from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup
from skill_evaluator.reporting.junit import JunitReporter


def _make_suite():
    return EvalSuite(
        suite="test suite",
        skill="./SKILL.md",
        defaults=SuiteDefaults(),
        tests=[],
    )


def _passing_result(name="test"):
    return TestResult(
        test_name=name,
        assertion_results=[
            AssertionResult(
                status=AssertionStatus.PASSED,
                assertion_type="stop_reason",
                message="ok",
            )
        ],
    )


def _failing_result(name="test"):
    return TestResult(
        test_name=name,
        assertion_results=[
            AssertionResult(
                status=AssertionStatus.FAILED,
                assertion_type="output_contains",
                message="Expected 'hello' not found",
            )
        ],
    )


def _error_result(name="test"):
    return TestResult(
        test_name=name,
        assertion_results=[
            AssertionResult(
                status=AssertionStatus.ERROR,
                assertion_type="execution",
                message="API error",
            )
        ],
    )


class TestJunitReporter:
    def test_single_passing_test(self):
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(test_name="greeting", runs=[_passing_result("greeting")]),
            ],
        )

        reporter = JunitReporter()
        root = reporter.build_report(suite, suite_result)

        assert root.tag == "testsuites"
        assert root.attrib["name"] == "test suite"

        testsuites = root.findall("testsuite")
        assert len(testsuites) == 1
        assert testsuites[0].attrib["failures"] == "0"
        assert testsuites[0].attrib["tests"] == "1"

        testcases = testsuites[0].findall("testcase")
        assert len(testcases) == 1
        assert testcases[0].attrib["name"] == "greeting"
        assert testcases[0].find("failure") is None

    def test_failing_test_has_failure_element(self):
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(test_name="bad test", runs=[_failing_result("bad test")]),
            ],
        )

        reporter = JunitReporter()
        root = reporter.build_report(suite, suite_result)

        ts = root.find("testsuite")
        assert ts.attrib["failures"] == "1"
        tc = ts.find("testcase")
        failure = tc.find("failure")
        assert failure is not None
        assert "hello" in failure.attrib["message"]
        assert failure.attrib["type"] == "output_contains"

    def test_error_test_has_error_element(self):
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(test_name="err test", runs=[_error_result("err test")]),
            ],
        )

        reporter = JunitReporter()
        root = reporter.build_report(suite, suite_result)

        tc = root.find(".//testcase")
        error = tc.find("error")
        assert error is not None
        assert "API" in error.attrib["message"]

    def test_multi_run_produces_n_testcases(self):
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(
                    test_name="multi",
                    runs=[
                        _passing_result("multi"),
                        _passing_result("multi"),
                        _failing_result("multi"),
                    ],
                ),
            ],
        )

        reporter = JunitReporter()
        root = reporter.build_report(suite, suite_result)

        ts = root.find("testsuite")
        assert ts.attrib["tests"] == "3"
        testcases = ts.findall("testcase")
        assert len(testcases) == 3
        assert testcases[0].attrib["name"] == "multi [run 0]"
        assert testcases[1].attrib["name"] == "multi [run 1]"
        assert testcases[2].attrib["name"] == "multi [run 2]"

    def test_baseline_produces_separate_testsuite(self):
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(
                    test_name="baseline test",
                    runs=[_passing_result("baseline test")],
                    baseline_runs=[_passing_result("baseline test")],
                ),
            ],
        )

        reporter = JunitReporter()
        root = reporter.build_report(suite, suite_result)

        testsuites = root.findall("testsuite")
        assert len(testsuites) == 2
        names = [ts.attrib["name"] for ts in testsuites]
        assert "baseline test" in names
        assert "baseline test [baseline]" in names

    def test_write_creates_valid_xml(self, tmp_path):
        suite = _make_suite()
        suite_result = SuiteResult(
            suite_name="test suite",
            test_results=[
                TestRunGroup(test_name="t1", runs=[_passing_result("t1")]),
            ],
        )

        reporter = JunitReporter()
        root = reporter.build_report(suite, suite_result)

        out_path = tmp_path / "results.xml"
        reporter.write(root, out_path)

        assert out_path.exists()
        # Verify it's parseable XML
        parsed = ET.parse(out_path)
        assert parsed.getroot().tag == "testsuites"

    def test_skipped_assertion(self):
        suite = _make_suite()
        result = TestResult(
            test_name="skipped",
            assertion_results=[
                AssertionResult(
                    status=AssertionStatus.SKIPPED,
                    assertion_type="llm_judge",
                    message="Not implemented",
                )
            ],
        )
        suite_result = SuiteResult(
            suite_name="test",
            test_results=[TestRunGroup(test_name="skipped", runs=[result])],
        )

        reporter = JunitReporter()
        root = reporter.build_report(suite, suite_result)

        tc = root.find(".//testcase")
        skipped = tc.find("skipped")
        assert skipped is not None
        assert skipped.attrib["message"] == "Not implemented"
