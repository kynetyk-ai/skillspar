"""Eval file discovery — resolve CLI arguments to .eval.yaml paths."""

from __future__ import annotations

import glob as globmod
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DiscoveryError(Exception):
    """Raised when no eval files can be resolved from the given arguments."""


def resolve_eval_paths(raw_paths: tuple[str, ...]) -> list[Path]:
    """Resolve CLI arguments (files, directories, globs) to eval file paths.

    Returns a deduplicated, sorted list of resolved .eval.yaml paths.
    Raises DiscoveryError if no eval files are found.
    """
    found: set[Path] = set()

    for raw in raw_paths:
        path = Path(raw)

        if path.is_dir():
            # Recursively find all .eval.yaml files
            matches = list(path.rglob("*.eval.yaml"))
            logger.debug("Directory %s: found %d eval file(s)", raw, len(matches))
            for m in matches:
                found.add(m.resolve())

        elif path.is_file():
            found.add(path.resolve())

        else:
            # Try glob expansion
            expanded = globmod.glob(raw, recursive=True)
            matches = [Path(p) for p in expanded if p.endswith(".eval.yaml") and Path(p).is_file()]
            logger.debug("Glob %s: expanded to %d eval file(s)", raw, len(matches))
            for m in matches:
                found.add(m.resolve())

    if not found:
        raise DiscoveryError(
            f"No .eval.yaml files found matching: {', '.join(raw_paths)}"
        )

    result = sorted(found)
    logger.info("Resolved %d eval file(s)", len(result))
    return result
