"""YAML loading and validation."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from skill_evaluator.config.schema import EvalSuite, ResolvedConfig, SuiteDefaults

logger = logging.getLogger(__name__)


class ConfigLoadError(Exception):
    """Raised when an eval suite configuration cannot be loaded."""


def resolve_skill_path(eval_file: Path, skill_ref: str) -> Path:
    """Resolve a skill path relative to the eval file's directory."""
    return (eval_file.parent / skill_ref).resolve()


def _apply_env_defaults(raw: dict) -> dict:
    """Inject env-var defaults into the raw YAML dict when keys are absent.

    Only fills in values that the YAML file didn't explicitly set.
    """
    defaults = raw.setdefault("defaults", {})

    env_model = os.environ.get("SKILLSPAR_MODEL")
    if env_model and "model" not in defaults:
        logger.debug("Injecting SKILLSPAR_MODEL=%s into defaults", env_model)
        defaults["model"] = env_model

    env_judge = os.environ.get("SKILLSPAR_JUDGE_MODEL")
    if env_judge and "judge_model" not in defaults:
        logger.debug("Injecting SKILLSPAR_JUDGE_MODEL=%s into defaults", env_judge)
        defaults["judge_model"] = env_judge

    return raw


def resolve_config(
    suite_defaults: SuiteDefaults,
    *,
    cli_runs: int | None = None,
    cli_concurrency: int | None = None,
    cli_model: str | None = None,
    cli_output: str | None = None,
    cli_output_format: str | None = None,
    cli_verbose: bool = False,
    cli_filter_pattern: str | None = None,
) -> ResolvedConfig:
    """Merge YAML-resolved defaults with env vars and CLI overrides.

    Precedence (lowest → highest): hardcoded → env vars → YAML → CLI flags.
    YAML defaults are already baked into *suite_defaults* (via _apply_env_defaults).
    This function layers CLI flags on top.
    """
    output = cli_output
    if output is None:
        output = os.environ.get("SKILLSPAR_OUTPUT")

    config = ResolvedConfig(
        system_prompt=suite_defaults.system_prompt,
        model=cli_model or suite_defaults.model,
        judge_model=suite_defaults.judge_model,
        max_tokens=suite_defaults.max_tokens,
        temperature=suite_defaults.temperature,
        runs=cli_runs if cli_runs is not None else suite_defaults.runs,
        pass_threshold=suite_defaults.pass_threshold,
        max_retries=suite_defaults.max_retries,
        concurrency=cli_concurrency if cli_concurrency is not None else suite_defaults.concurrency,
        enable_caching=suite_defaults.enable_caching,
        output=output,
        output_format=cli_output_format or "json",
        verbose=cli_verbose,
        filter_pattern=cli_filter_pattern,
    )
    logger.debug(
        "Resolved config: model=%s, runs=%d, concurrency=%d, output=%s",
        config.model, config.runs, config.concurrency, config.output,
    )
    return config


def load_eval_suite(path: str | Path) -> EvalSuite:
    """Load and validate an eval suite from a YAML file.

    Returns a validated ``EvalSuite`` model. Raises ``ConfigLoadError``
    on any parsing or validation failure.
    """
    path = Path(path)
    if not path.exists():
        raise ConfigLoadError(f"Eval file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigLoadError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigLoadError(f"Expected a YAML mapping in {path}")

    logger.debug("Raw YAML has %d test(s)", len(raw.get("tests", [])))
    _apply_env_defaults(raw)

    try:
        suite = EvalSuite.model_validate(raw)
    except ValidationError as e:
        raise ConfigLoadError(f"Validation error in {path}: {e}") from e

    # Verify skill file exists
    skill_path = resolve_skill_path(path, suite.skill)
    if not skill_path.exists():
        raise ConfigLoadError(f"Skill file not found: {skill_path} (referenced in {path})")

    logger.info(
        "Loaded suite '%s' (%d tests, model=%s)",
        suite.suite, len(suite.tests), suite.defaults.model,
    )
    return suite
