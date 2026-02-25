"""JUnit XML output for CI integration."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from skill_evaluator.assertions.base import AssertionStatus
from skill_evaluator.config.schema import EvalSuite
from skill_evaluator.reporting.console import SuiteResult, TestRunGroup


class JunitReporter:
    """Builds and writes JUnit XML reports from suite results."""

    def build_report(self, suite: EvalSuite, suite_result: SuiteResult) -> ET.Element:
        """Build a JUnit XML element tree from suite results."""
        root = ET.Element("testsuites", name=suite.suite)

        for group in suite_result.test_results:
            self._add_test_group(root, group)
            if group.baseline_runs:
                self._add_baseline_group(root, group)

        return root

    def _add_test_group(self, root: ET.Element, group: TestRunGroup) -> None:
        failures = sum(1 for r in group.runs if not r.passed)
        errors = 0
        for run in group.runs:
            for ar in run.assertion_results:
                if ar.status == AssertionStatus.ERROR:
                    errors += 1
                    break

        ts_attrs: dict[str, str] = {
            "name": group.test_name,
            "tests": str(len(group.runs)),
            "failures": str(failures),
            "errors": str(errors),
        }
        group_duration = group.duration_seconds
        if group_duration is not None:
            ts_attrs["time"] = f"{group_duration:.3f}"
        ts = ET.SubElement(root, "testsuite", **ts_attrs)

        if group.is_multi_run:
            for i, run in enumerate(group.runs):
                tc_attrs: dict[str, str] = {"name": f"{group.test_name} [run {i}]"}
                if run.duration_seconds is not None:
                    tc_attrs["time"] = f"{run.duration_seconds:.3f}"
                tc = ET.SubElement(ts, "testcase", **tc_attrs)
                self._add_assertion_elements(tc, run)
        else:
            tc_attrs = {"name": group.test_name}
            if group.runs[0].duration_seconds is not None:
                tc_attrs["time"] = f"{group.runs[0].duration_seconds:.3f}"
            tc = ET.SubElement(ts, "testcase", **tc_attrs)
            self._add_assertion_elements(tc, group.runs[0])

    def _add_baseline_group(self, root: ET.Element, group: TestRunGroup) -> None:
        baseline_runs = group.baseline_runs
        failures = sum(1 for r in baseline_runs if not r.passed)
        errors = 0
        for run in baseline_runs:
            for ar in run.assertion_results:
                if ar.status == AssertionStatus.ERROR:
                    errors += 1
                    break

        bl_durations = [r.duration_seconds for r in baseline_runs if r.duration_seconds is not None]
        ts_attrs: dict[str, str] = {
            "name": f"{group.test_name} [baseline]",
            "tests": str(len(baseline_runs)),
            "failures": str(failures),
            "errors": str(errors),
        }
        if bl_durations:
            ts_attrs["time"] = f"{sum(bl_durations):.3f}"
        ts = ET.SubElement(root, "testsuite", **ts_attrs)

        for i, run in enumerate(baseline_runs):
            tc_attrs: dict[str, str] = {"name": f"{group.test_name} [baseline run {i}]"}
            if run.duration_seconds is not None:
                tc_attrs["time"] = f"{run.duration_seconds:.3f}"
            tc = ET.SubElement(ts, "testcase", **tc_attrs)
            self._add_assertion_elements(tc, run)

    def _add_assertion_elements(self, testcase: ET.Element, run) -> None:
        for ar in run.assertion_results:
            if ar.status == AssertionStatus.FAILED:
                failure = ET.SubElement(
                    testcase, "failure",
                    message=ar.message,
                    type=ar.assertion_type,
                )
                failure.text = ar.message
            elif ar.status == AssertionStatus.ERROR:
                error = ET.SubElement(
                    testcase, "error",
                    message=ar.message,
                )
                error.text = ar.message
            elif ar.status == AssertionStatus.SKIPPED:
                ET.SubElement(testcase, "skipped", message=ar.message)

    def write(self, report: ET.Element, path: Path) -> None:
        """Write XML report to file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tree = ET.ElementTree(report)
        ET.indent(tree, space="  ")
        tree.write(path, encoding="unicode", xml_declaration=True)
