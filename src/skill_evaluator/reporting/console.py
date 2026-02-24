"""Rich terminal output for test results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rich.console import Console

from skill_evaluator.assertions.base import AssertionResult, AssertionStatus

if TYPE_CHECKING:
    from skill_evaluator.engine.trace import Trace


@dataclass
class TestResult:
    test_name: str
    assertion_results: list[AssertionResult] = field(default_factory=list)
    trace: Trace | None = None

    @property
    def passed(self) -> bool:
        return all(
            r.status in (AssertionStatus.PASSED, AssertionStatus.SKIPPED)
            for r in self.assertion_results
        )

    @property
    def status_label(self) -> str:
        if not self.assertion_results:
            return "SKIP"
        return "PASS" if self.passed else "FAIL"

    def to_dict(self) -> dict:
        return {
            "assertions": [
                {
                    "type": r.assertion_type,
                    "status": r.status.value,
                    "message": r.message,
                    "details": r.details,
                }
                for r in self.assertion_results
            ],
            "passed": self.passed,
            "trace": self.trace.to_dict() if self.trace else None,
        }


@dataclass
class TestRunGroup:
    test_name: str
    runs: list[TestResult]
    baseline_runs: list[TestResult] | None = None
    pass_threshold: float = 1.0

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.runs if r.passed)

    @property
    def pass_rate(self) -> float:
        if not self.runs:
            return 0.0
        return self.pass_count / len(self.runs)

    @property
    def passed(self) -> bool:
        return self.pass_rate >= self.pass_threshold

    @property
    def is_multi_run(self) -> bool:
        return len(self.runs) > 1

    @property
    def baseline_pass_count(self) -> int:
        if not self.baseline_runs:
            return 0
        return sum(1 for r in self.baseline_runs if r.passed)

    @property
    def status_label(self) -> str:
        if not self.is_multi_run:
            return self.runs[0].status_label
        return "PASS" if self.passed else "FAIL"

    def to_dict(self) -> dict:
        total = len(self.runs)
        result: dict = {
            "name": self.test_name,
            "config": {
                "runs": total,
                "pass_threshold": self.pass_threshold,
                "baseline": self.baseline_runs is not None,
            },
            "summary": {
                "pass_count": self.pass_count,
                "total_runs": total,
                "pass_rate": self.pass_rate,
                "passed": self.passed,
            },
            "runs": [
                {"run_index": i, **r.to_dict()} for i, r in enumerate(self.runs)
            ],
        }
        if self.baseline_runs is not None:
            bl_total = len(self.baseline_runs)
            bl_pass = self.baseline_pass_count
            result["baseline_runs"] = [
                {"run_index": i, **r.to_dict()} for i, r in enumerate(self.baseline_runs)
            ]
            result["baseline_summary"] = {
                "pass_count": bl_pass,
                "total_runs": bl_total,
                "pass_rate": bl_pass / bl_total if bl_total else 0.0,
            }
        return result


@dataclass
class SuiteResult:
    suite_name: str
    test_results: list[TestRunGroup] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for t in self.test_results if t.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for t in self.test_results if not t.passed)

    @property
    def all_passed(self) -> bool:
        return all(t.passed for t in self.test_results)


class ConsoleReporter:
    """Renders test results to the terminal using Rich."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def report(self, suite_result: SuiteResult) -> None:
        self.console.print()
        self.console.print(f"[bold]Suite: {suite_result.suite_name}[/bold]")
        self.console.print()

        for group in suite_result.test_results:
            if group.is_multi_run:
                self._report_multi_run(group)
            else:
                self._report_single_run(group)

        self.console.print()
        total = len(suite_result.test_results)
        passed = suite_result.passed_count
        failed = suite_result.failed_count

        if suite_result.all_passed:
            self.console.print(f"[green bold]{passed}/{total} tests passed[/green bold]")
        else:
            self.console.print(
                f"[red bold]{failed}/{total} tests failed[/red bold], "
                f"{passed}/{total} passed"
            )

    def _report_single_run(self, group: TestRunGroup) -> None:
        test = group.runs[0]
        if test.passed:
            self.console.print(f"  [green]✓[/green] {group.test_name}")
        else:
            self.console.print(f"  [red]✗[/red] {group.test_name}")
            for result in test.assertion_results:
                if result.status == AssertionStatus.FAILED:
                    self.console.print(f"    [red]FAIL[/red] {result.message}")
                elif result.status == AssertionStatus.ERROR:
                    self.console.print(f"    [yellow]ERROR[/yellow] {result.message}")

    def _report_multi_run(self, group: TestRunGroup) -> None:
        total = len(group.runs)
        pc = group.pass_count
        if group.passed:
            self.console.print(
                f"  [green]✓[/green] {group.test_name}  {pc}/{total} passed"
            )
        else:
            threshold_pct = int(group.pass_threshold * 100)
            self.console.print(
                f"  [red]✗[/red] {group.test_name}  "
                f"{pc}/{total} passed (threshold: {threshold_pct}%)"
            )
        if group.baseline_runs is not None:
            bl_total = len(group.baseline_runs)
            bl_pass = group.baseline_pass_count
            self.console.print(
                f"    [dim]baseline: {bl_pass}/{bl_total} passed[/dim]"
            )
