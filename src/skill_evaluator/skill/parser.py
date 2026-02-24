"""SKILL.md frontmatter and body extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class SkillParseError(Exception):
    """Raised when a SKILL.md file cannot be parsed."""


@dataclass(frozen=True)
class ParsedSkill:
    name: str
    description: str
    metadata: dict[str, Any]
    body: str
    source_path: Path


def parse_skill(path: Path) -> ParsedSkill:
    """Parse a SKILL.md file into a ParsedSkill.

    Expects YAML frontmatter delimited by ``---`` lines, followed by
    a markdown body that will be used as the system prompt.
    """
    path = Path(path)
    if not path.exists():
        raise SkillParseError(f"Skill file not found: {path}")

    text = path.read_text(encoding="utf-8")

    if not text.startswith("---"):
        raise SkillParseError(f"Skill file missing frontmatter delimiters: {path}")

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SkillParseError(f"Skill file has incomplete frontmatter: {path}")

    # parts[0] is empty (before first ---), parts[1] is frontmatter, parts[2] is body
    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        raise SkillParseError(f"Invalid YAML frontmatter in {path}: {e}") from e

    if not isinstance(frontmatter, dict):
        raise SkillParseError(f"Frontmatter must be a YAML mapping in {path}")

    body = parts[2].strip()

    return ParsedSkill(
        name=frontmatter.get("name", path.stem),
        description=frontmatter.get("description", ""),
        metadata=frontmatter,
        body=body,
        source_path=path,
    )
