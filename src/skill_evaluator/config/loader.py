"""YAML loading and validation."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from skill_evaluator.config.schema import EvalSuite


class ConfigLoadError(Exception):
    """Raised when an eval suite configuration cannot be loaded."""


def resolve_skill_path(eval_file: Path, skill_ref: str) -> Path:
    """Resolve a skill path relative to the eval file's directory."""
    return (eval_file.parent / skill_ref).resolve()


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

    try:
        suite = EvalSuite.model_validate(raw)
    except ValidationError as e:
        raise ConfigLoadError(f"Validation error in {path}: {e}") from e

    # Verify skill file exists
    skill_path = resolve_skill_path(path, suite.skill)
    if not skill_path.exists():
        raise ConfigLoadError(f"Skill file not found: {skill_path} (referenced in {path})")

    return suite
