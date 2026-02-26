"""Top-level orchestrator for running eval suites."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from skill_evaluator.assertions.evaluator import evaluate_assertions
from skill_evaluator.config.loader import resolve_skill_path
from skill_evaluator.config.schema import (
    EvalSuite,
    InputConfig,
    MessageConfig,
    MultiTurnTest,
    ResolvedConfig,
    SingleTurnTest,
)
from skill_evaluator.engine.context import ContextFileError, build_context_messages
from skill_evaluator.engine.conversation import build_skill_messages
from skill_evaluator.engine.multi_turn import MultiTurnExecutor
from skill_evaluator.engine.prefix import (
    MINIMUM_CACHE_TOKEN_THRESHOLD,
    PrefixLoadError,
    estimate_prefix_tokens,
    load_prefix_messages,
)
from skill_evaluator.engine.single_turn import SingleTurnExecutor
from skill_evaluator.reporting.console import SuiteResult, TestResult, TestRunGroup
from skill_evaluator.skill.parser import parse_skill
from skill_evaluator.tools.registry import resolve_tools

logger = logging.getLogger(__name__)


@dataclass
class _WorkItem:
    test_index: int
    test: SingleTurnTest | MultiTurnTest
    run_index: int
    is_baseline: bool
    skill_body: str


class SuiteRunner:
    """Orchestrates running all tests in an eval suite."""

    def __init__(
        self,
        eval_file: Path,
        suite: EvalSuite,
        client: Anthropic | None = None,
        config: ResolvedConfig | None = None,
    ) -> None:
        self.eval_file = Path(eval_file)
        self.suite = suite
        # Build ResolvedConfig from suite.defaults when not provided (backward compat)
        if config is None:
            config = ResolvedConfig(
                system_prompt=suite.defaults.system_prompt,
                model=suite.defaults.model,
                judge_model=suite.defaults.judge_model,
                max_tokens=suite.defaults.max_tokens,
                temperature=suite.defaults.temperature,
                runs=suite.defaults.runs,
                pass_threshold=suite.defaults.pass_threshold,
                max_retries=suite.defaults.max_retries,
                concurrency=suite.defaults.concurrency,
                enable_caching=suite.defaults.enable_caching,
            )
        self.config = config
        self.client = client or Anthropic(max_retries=self.config.max_retries)

    def _effective_runs(self, test: SingleTurnTest | MultiTurnTest) -> int:
        return test.runs if test.runs is not None else self.config.runs

    def _effective_threshold(self, test: SingleTurnTest | MultiTurnTest) -> float:
        return (
            test.pass_threshold
            if test.pass_threshold is not None
            else self.config.pass_threshold
        )

    def _build_system_prompt(self) -> str | list[dict]:
        """Build the system prompt, optionally as structured content with cache_control."""
        prompt = self.config.system_prompt
        if self.config.enable_caching and prompt:
            return [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]
        return prompt

    def _skill_cache_control(self) -> dict[str, str] | None:
        """Return cache_control for the skill message when a prefix is present and caching is on."""
        if not self.config.enable_caching or self.suite.conversation_prefix is None:
            return None
        return {"type": "ephemeral"}

    def _merge_messages(
        self,
        skill_messages: list[MessageConfig],
        prefix_messages: list[MessageConfig],
        context_messages: list[MessageConfig],
        test_messages: list[MessageConfig],
    ) -> list[MessageConfig]:
        """Merge skill, prefix, context, and test messages in the correct order."""
        if (
            self.suite.conversation_prefix
            and self.suite.conversation_prefix.skill_position == "bottom"
        ):
            return prefix_messages + skill_messages + context_messages + test_messages
        return skill_messages + prefix_messages + context_messages + test_messages

    def run(self) -> SuiteResult:
        """Run all tests and return results."""
        run_id = str(uuid.uuid4())
        logger.info("Starting suite '%s' (%d tests) run_id=%s", self.suite.suite, len(self.suite.tests), run_id)
        skill_path = resolve_skill_path(self.eval_file, self.suite.skill)
        skill = parse_skill(skill_path)
        skill_body = skill.body
        skill_file_hash = hashlib.sha256(skill_path.read_bytes()).hexdigest()

        suite_tools = resolve_tools(self.suite.tools)

        # Load conversation prefix (once, shared across all tests)
        self._prefix_messages: list[MessageConfig] = []
        if self.suite.conversation_prefix is not None:
            # Cache the prefix as a shared breakpoint across all runs.
            # In bottom mode (Prefix → Skill → ...), both prefix and skill
            # get independent cache_control markers — the API supports
            # multiple breakpoints, so consecutive skill runs cache both
            # and baseline runs still hit the prefix cache.
            prefix_caching = self.config.enable_caching
            try:
                self._prefix_messages = load_prefix_messages(
                    self.eval_file,
                    self.suite.conversation_prefix,
                    enable_caching=prefix_caching,
                )
                token_est = estimate_prefix_tokens(self._prefix_messages)
                if token_est < MINIMUM_CACHE_TOKEN_THRESHOLD:
                    logger.warning(
                        "Prefix estimated at ~%d tokens, below minimum cache threshold of %d. "
                        "Caching may not activate.",
                        token_est, MINIMUM_CACHE_TOKEN_THRESHOLD,
                    )
            except PrefixLoadError as e:
                logger.error("Failed to load conversation prefix: %s", e)
                raise

        # Build work items — grouped by variant for cache efficiency.
        # All skill runs first, then all baseline runs, so consecutive
        # API calls share the same message prefix and hit the cache.
        work_items: list[_WorkItem] = []

        # Pass 1: skill runs
        for idx, test in enumerate(self.suite.tests):
            runs = self._effective_runs(test)
            for run_i in range(runs):
                work_items.append(
                    _WorkItem(idx, test, run_i, is_baseline=False, skill_body=skill_body)
                )

        # Pass 2: baseline runs
        for idx, test in enumerate(self.suite.tests):
            if not test.baseline:
                continue
            runs = self._effective_runs(test)
            for run_i in range(runs):
                work_items.append(
                    _WorkItem(idx, test, run_i, is_baseline=True, skill_body="")
                )

        logger.debug("Built %d work items", len(work_items))

        # Execute work items
        results_map: dict[tuple[int, int, bool], TestResult] = {}
        concurrency = self.config.concurrency

        if concurrency <= 1:
            for item in work_items:
                result = self._execute_work_item(item, suite_tools)
                results_map[(item.test_index, item.run_index, item.is_baseline)] = result
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                future_to_item = {
                    pool.submit(self._execute_work_item, item, suite_tools): item
                    for item in work_items
                }
                for future in as_completed(future_to_item):
                    item = future_to_item[future]
                    results_map[(item.test_index, item.run_index, item.is_baseline)] = (
                        future.result()
                    )

        # Assemble into TestRunGroups
        suite_result = SuiteResult(
            suite_name=self.suite.suite,
            run_id=run_id,
            skill_file_hash=skill_file_hash,
        )
        for idx, test in enumerate(self.suite.tests):
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

        passed = sum(1 for g in suite_result.test_results if g.passed)
        logger.info(
            "Suite '%s' complete: %d/%d tests passed",
            self.suite.suite, passed, len(suite_result.test_results),
        )
        return suite_result

    def _execute_work_item(
        self, item: _WorkItem, suite_tools: list[dict[str, Any]]
    ) -> TestResult:
        logger.debug(
            "Dispatching test '%s' run=%d baseline=%s",
            item.test.name, item.run_index, item.is_baseline,
        )
        if isinstance(item.test, MultiTurnTest):
            return self._run_multi_turn(item.test, item.skill_body, suite_tools)
        return self._run_single_turn(item.test, item.skill_body, suite_tools)

    def _resolve_context_for(
        self, test: SingleTurnTest | MultiTurnTest
    ) -> list[MessageConfig]:
        """Merge suite-level and test-level context, build synthetic messages."""
        context_files = list(self.suite.context or []) + list(test.context or [])
        if not context_files:
            return []
        return build_context_messages(self.eval_file, context_files)

    def _run_single_turn(
        self,
        test: SingleTurnTest,
        skill_body: str,
        suite_tools: list[dict[str, Any]],
    ) -> TestResult:
        """Execute a single-turn test and evaluate its assertions."""
        try:
            context_messages = self._resolve_context_for(test)
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

        skill_cache = self._skill_cache_control()
        skill_messages = build_skill_messages(skill_body, cache_control=skill_cache) if skill_body else []
        prefix_messages = list(self._prefix_messages)
        test_messages = list(test.input.messages)
        if not skill_body:  # baseline run — strip skill-only messages
            test_messages = [m for m in test_messages if not m.skill_only]
        merged_messages = self._merge_messages(skill_messages, prefix_messages, context_messages, test_messages)
        input_config = InputConfig(messages=merged_messages)

        system_prompt = self._build_system_prompt()
        executor = SingleTurnExecutor(self.client, self.config)
        t0 = time.monotonic()
        try:
            trace = executor.execute(
                system_prompt, input_config, tools=suite_tools or None
            )
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
                duration_seconds=time.monotonic() - t0,
            )
        duration = time.monotonic() - t0

        assertion_results = evaluate_assertions(
            test.assertions, trace,
            client=self.client,
            judge_model=self.config.judge_model or self.config.model,
        )
        return TestResult(
            test_name=test.name,
            assertion_results=assertion_results,
            trace=trace,
            duration_seconds=duration,
        )

    def _run_multi_turn(
        self,
        test: MultiTurnTest,
        skill_body: str,
        suite_tools: list[dict[str, Any]],
    ) -> TestResult:
        """Execute a multi-turn test and evaluate its assertions."""
        try:
            context_messages = self._resolve_context_for(test)
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

        skill_cache = self._skill_cache_control()
        skill_messages = build_skill_messages(skill_body, cache_control=skill_cache) if skill_body else []
        prefix_messages = list(self._prefix_messages)
        test_messages = list(test.input.messages)
        if not skill_body:  # baseline run — strip skill-only messages
            test_messages = [m for m in test_messages if not m.skill_only]
        merged_messages = self._merge_messages(skill_messages, prefix_messages, context_messages, test_messages)
        input_config = InputConfig(messages=merged_messages)

        system_prompt = self._build_system_prompt()
        executor = MultiTurnExecutor(
            client=self.client,
            config=self.config,
            tools=suite_tools or None,
            tool_responses=test.tool_responses,
            max_turns=test.max_turns,
        )

        t0 = time.monotonic()
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
                duration_seconds=time.monotonic() - t0,
            )
        duration = time.monotonic() - t0

        assertion_results = evaluate_assertions(
            test.assertions, trace,
            client=self.client,
            judge_model=self.config.judge_model or self.config.model,
        )
        return TestResult(
            test_name=test.name,
            assertion_results=assertion_results,
            trace=trace,
            duration_seconds=duration,
        )
