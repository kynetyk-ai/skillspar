"""Multi-suite runner — execute multiple eval suites sequentially."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skill_evaluator.config.loader import ConfigLoadError, load_eval_suite, resolve_config
from skill_evaluator.config.schema import EvalSuite, ResolvedConfig
from skill_evaluator.engine.prefix import PrefixLoadError
from skill_evaluator.executor import execute_suite
from skill_evaluator.providers import missing_api_key_error
from skill_evaluator.reporting.console import SuiteResult
from skill_evaluator.reporting.cost import build_cache_summary, build_cost_summary
from skill_evaluator.skill.parser import SkillParseError

logger = logging.getLogger(__name__)


@dataclass
class SuiteOutcome:
    """Result container for a single suite within a multi-suite run."""

    eval_file: Path
    suite: EvalSuite | None = None
    suite_result: SuiteResult | None = None
    config: ResolvedConfig | None = None
    cost_summary: dict[str, Any] | None = None
    cache_summary: dict[str, Any] | None = None
    error: str | None = None

    @property
    def passed(self) -> bool:
        if self.error is not None or self.suite_result is None:
            return False
        return self.suite_result.all_passed

    @property
    def suite_name(self) -> str:
        if self.suite is not None:
            return self.suite.suite
        return self.eval_file.stem


@dataclass
class MultiSuiteResult:
    """Aggregated result across all suites in a multi-suite run."""

    outcomes: list[SuiteOutcome] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(o.passed for o in self.outcomes)

    @property
    def total_suites(self) -> int:
        return len(self.outcomes)

    @property
    def passed_suites(self) -> int:
        return sum(1 for o in self.outcomes if o.passed)

    @property
    def failed_suites(self) -> int:
        return sum(
            1
            for o in self.outcomes
            if not o.passed and o.error is None and o.suite_result is not None
        )

    @property
    def error_suites(self) -> int:
        return sum(1 for o in self.outcomes if o.error is not None)

    @property
    def has_config_errors(self) -> bool:
        return self.error_suites > 0


def run_suites(
    eval_files: list[Path],
    *,
    cli_runs: int | None = None,
    cli_concurrency: int | None = None,
    cli_model: str | None = None,
    cli_provider: str | None = None,
    cli_base_url: str | None = None,
    cli_output: str | None = None,
    cli_output_format: str | None = None,
    cli_verbose: bool = False,
    cli_filter_pattern: str | None = None,
) -> MultiSuiteResult:
    """Run multiple eval suites sequentially.

    Each suite is loaded, configured, and executed independently.
    A failure in one suite does not abort subsequent suites.
    """
    result = MultiSuiteResult()

    for eval_file in eval_files:
        outcome = _run_single(
            eval_file,
            cli_runs=cli_runs,
            cli_concurrency=cli_concurrency,
            cli_model=cli_model,
            cli_provider=cli_provider,
            cli_base_url=cli_base_url,
            cli_output=cli_output,
            cli_output_format=cli_output_format,
            cli_verbose=cli_verbose,
            cli_filter_pattern=cli_filter_pattern,
        )
        result.outcomes.append(outcome)

    return result


def _run_single(
    eval_file: Path,
    *,
    cli_runs: int | None = None,
    cli_concurrency: int | None = None,
    cli_model: str | None = None,
    cli_provider: str | None = None,
    cli_base_url: str | None = None,
    cli_output: str | None = None,
    cli_output_format: str | None = None,
    cli_verbose: bool = False,
    cli_filter_pattern: str | None = None,
) -> SuiteOutcome:
    """Execute a single suite, capturing all expected errors."""
    try:
        suite = load_eval_suite(eval_file)
    except ConfigLoadError as e:
        logger.warning("Config error in %s: %s", eval_file, e)
        return SuiteOutcome(eval_file=eval_file, error=str(e))

    config = resolve_config(
        suite.defaults,
        cli_runs=cli_runs,
        cli_concurrency=cli_concurrency,
        cli_model=cli_model,
        cli_provider=cli_provider,
        cli_base_url=cli_base_url,
        cli_output=cli_output,
        cli_output_format=cli_output_format,
        cli_verbose=cli_verbose,
        cli_filter_pattern=cli_filter_pattern,
    )

    key_error = missing_api_key_error(config.provider, config.api_key_env)
    if key_error:
        logger.warning("Missing API key for %s: %s", eval_file, key_error)
        return SuiteOutcome(eval_file=eval_file, suite=suite, config=config, error=key_error)

    # Filter tests by name substring
    if cli_filter_pattern is not None:
        pattern_lower = cli_filter_pattern.lower()
        suite.tests = [t for t in suite.tests if pattern_lower in t.name.lower()]
        if not suite.tests:
            return SuiteOutcome(
                eval_file=eval_file,
                suite=suite,
                config=config,
                error=f"No tests match filter '{cli_filter_pattern}'",
            )

    try:
        suite_result = execute_suite(eval_file, suite, config)
    except (SkillParseError, PrefixLoadError) as e:
        logger.warning("Execution error in %s: %s", eval_file, e)
        return SuiteOutcome(eval_file=eval_file, suite=suite, config=config, error=str(e))
    except Exception as e:
        logger.warning("Unexpected error in %s: %s", eval_file, e)
        msg = f"Unexpected error: {e}"
        return SuiteOutcome(eval_file=eval_file, suite=suite, config=config, error=msg)

    cost_summary = build_cost_summary(suite_result, config.model)
    cache_summary = (
        build_cache_summary(suite_result, config.model) if config.provider == "anthropic" else None
    )

    return SuiteOutcome(
        eval_file=eval_file,
        suite=suite,
        suite_result=suite_result,
        config=config,
        cost_summary=cost_summary,
        cache_summary=cache_summary,
    )
