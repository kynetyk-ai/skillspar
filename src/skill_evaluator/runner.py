"""Top-level orchestrator for running eval suites."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from anthropic import Anthropic

from skill_evaluator.assertions.evaluator import evaluate_assertions
from skill_evaluator.config.loader import resolve_skill_path
from skill_evaluator.config.schema import (
    EvalSuite,
    InputConfig,
    MessageConfig,
    SingleTurnTest,
)
from skill_evaluator.engine.context import ContextFileError, build_context_messages
from skill_evaluator.engine.single_turn import SingleTurnExecutor
from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup
from skill_evaluator.skill.parser import parse_skill


@dataclass
class _WorkItem:
    test_index: int
    test: SingleTurnTest
    run_index: int
    is_baseline: bool
    system_prompt: str


class SuiteRunner:
    """Orchestrates running all tests in an eval suite."""

    def __init__(
        self,
        eval_file: Path,
        suite: EvalSuite,
        client: Anthropic | None = None,
    ) -> None:
        self.eval_file = Path(eval_file)
        self.suite = suite
        self.client = client or Anthropic(max_retries=suite.defaults.max_retries)

    def _effective_runs(self, test: SingleTurnTest) -> int:
        return test.runs if test.runs is not None else self.suite.defaults.runs

    def _effective_threshold(self, test: SingleTurnTest) -> float:
        return (
            test.pass_threshold
            if test.pass_threshold is not None
            else self.suite.defaults.pass_threshold
        )

    def run(self) -> SuiteResult:
        """Run all tests and return results."""
        skill_path = resolve_skill_path(self.eval_file, self.suite.skill)
        skill = parse_skill(skill_path)
        system_prompt = skill.body

        executor = SingleTurnExecutor(self.client, self.suite.defaults)

        # Build work items
        work_items: list[_WorkItem] = []
        for idx, test in enumerate(self.suite.tests):
            if not isinstance(test, SingleTurnTest):
                continue
            runs = self._effective_runs(test)
            for run_i in range(runs):
                work_items.append(
                    _WorkItem(idx, test, run_i, is_baseline=False, system_prompt=system_prompt)
                )
                if test.baseline:
                    work_items.append(
                        _WorkItem(idx, test, run_i, is_baseline=True, system_prompt="")
                    )

        # Execute work items
        results_map: dict[tuple[int, int, bool], TestResult] = {}
        concurrency = self.suite.defaults.concurrency

        if concurrency <= 1:
            for item in work_items:
                result = self._execute_work_item(item, executor)
                results_map[(item.test_index, item.run_index, item.is_baseline)] = result
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                future_to_item = {
                    pool.submit(self._execute_work_item, item, executor): item
                    for item in work_items
                }
                for future in as_completed(future_to_item):
                    item = future_to_item[future]
                    results_map[(item.test_index, item.run_index, item.is_baseline)] = (
                        future.result()
                    )

        # Assemble into TestRunGroups
        suite_result = SuiteResult(suite_name=self.suite.suite)
        for idx, test in enumerate(self.suite.tests):
            if not isinstance(test, SingleTurnTest):
                group = TestRunGroup(
                    test_name=test.name,
                    runs=[TestResult(test_name=test.name)],
                )
                suite_result.test_results.append(group)
                continue

            runs_count = self._effective_runs(test)
            threshold = self._effective_threshold(test)

            skill_runs = [
                results_map[(idx, ri, False)] for ri in range(runs_count)
            ]
            baseline_runs = None
            if test.baseline:
                baseline_runs = [
                    results_map[(idx, ri, True)] for ri in range(runs_count)
                ]

            group = TestRunGroup(
                test_name=test.name,
                runs=skill_runs,
                baseline_runs=baseline_runs,
                pass_threshold=threshold,
            )
            suite_result.test_results.append(group)

        return suite_result

    def _execute_work_item(
        self, item: _WorkItem, executor: SingleTurnExecutor
    ) -> TestResult:
        return self._run_single_turn(item.test, executor, item.system_prompt)

    def _resolve_context(self, test: SingleTurnTest) -> list[MessageConfig]:
        """Merge suite-level and test-level context, build synthetic messages."""
        context_files = list(self.suite.context or []) + list(test.context or [])
        if not context_files:
            return []
        return build_context_messages(self.eval_file, context_files)

    def _run_single_turn(
        self,
        test: SingleTurnTest,
        executor: SingleTurnExecutor,
        system_prompt: str,
    ) -> TestResult:
        """Execute a single-turn test and evaluate its assertions."""
        try:
            context_messages = self._resolve_context(test)
        except ContextFileError as e:
            from skill_evaluator.assertions.base import AssertionResult, AssertionStatus

            return TestResult(
                test_name=test.name,
                assertion_results=[
                    AssertionResult(
                        status=AssertionStatus.ERROR,
                        assertion_type="context",
                        message=f"Context file error: {e}",
                    )
                ],
            )

        input_config = test.input
        if context_messages:
            merged_messages = context_messages + list(test.input.messages)
            input_config = InputConfig(messages=merged_messages)

        try:
            trace = executor.execute(system_prompt, input_config)
        except Exception as e:
            from skill_evaluator.assertions.base import AssertionResult, AssertionStatus

            return TestResult(
                test_name=test.name,
                assertion_results=[
                    AssertionResult(
                        status=AssertionStatus.ERROR,
                        assertion_type="execution",
                        message=f"Execution failed: {e}",
                    )
                ],
            )

        assertion_results = evaluate_assertions(test.assertions, trace)
        return TestResult(test_name=test.name, assertion_results=assertion_results, trace=trace)
