"""Snapshot I/O — save, load, list, and find snapshots."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_SNAPSHOT_DIR = Path(".skillspar/snapshots")


class SnapshotLoadError(Exception):
    """Raised when a snapshot file cannot be loaded or is malformed."""


@dataclass
class SnapshotInfo:
    """Metadata about a saved snapshot file."""

    __test__ = False

    path: Path
    suite_name: str
    timestamp: str
    run_id: str | None


def _slugify(name: str) -> str:
    """Convert a name to a filename-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


def _resolve_snapshot_dir(snapshot_dir: Path | None) -> Path:
    """Resolve the snapshot directory, respecting env var override."""
    import os

    env_dir = os.environ.get("SKILLSPAR_SNAPSHOT_DIR")
    if snapshot_dir is not None:
        return snapshot_dir
    if env_dir:
        return Path(env_dir)
    return DEFAULT_SNAPSHOT_DIR


def save_snapshot(report: dict, snapshot_dir: Path | None = None) -> Path:
    """Save a JSON report dict as a snapshot file.

    Returns the path of the written snapshot.
    """
    resolved_dir = _resolve_snapshot_dir(snapshot_dir)
    resolved_dir.mkdir(parents=True, exist_ok=True)

    suite_name = report.get("suite", "unknown")
    slug = _slugify(suite_name)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"{slug}_{timestamp}.json"

    path = resolved_dir / filename
    with open(path, "w") as f:
        json.dump(report, f, indent=2)

    return path


def load_snapshot(path: Path) -> dict:
    """Load and validate a snapshot file.

    Raises SnapshotLoadError if the file is missing or malformed.
    """
    path = Path(path)
    if not path.exists():
        raise SnapshotLoadError(f"Snapshot file not found: {path}")

    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise SnapshotLoadError(f"Failed to read snapshot {path}: {e}") from e

    if not isinstance(data, dict):
        raise SnapshotLoadError(f"Snapshot is not a JSON object: {path}")
    if "schema_version" not in data:
        raise SnapshotLoadError(f"Snapshot missing schema_version: {path}")

    return data


def list_snapshots(
    suite_name: str | None = None, snapshot_dir: Path | None = None
) -> list[SnapshotInfo]:
    """List saved snapshots, newest first.

    Optionally filter by suite name.
    """
    resolved_dir = _resolve_snapshot_dir(snapshot_dir)
    if not resolved_dir.exists():
        return []

    snapshots: list[SnapshotInfo] = []
    for p in resolved_dir.glob("*.json"):
        try:
            data = load_snapshot(p)
        except SnapshotLoadError:
            continue

        snap_suite = data.get("suite", "")
        if suite_name is not None and snap_suite != suite_name:
            continue

        snapshots.append(
            SnapshotInfo(
                path=p,
                suite_name=snap_suite,
                timestamp=data.get("timestamp", ""),
                run_id=data.get("run_id"),
            )
        )

    # Sort newest first by timestamp string (ISO format sorts lexicographically)
    snapshots.sort(key=lambda s: s.timestamp, reverse=True)
    return snapshots


def find_latest_snapshot(suite_name: str, snapshot_dir: Path | None = None) -> Path | None:
    """Return the path of the most recent snapshot for a suite, or None."""
    snaps = list_snapshots(suite_name=suite_name, snapshot_dir=snapshot_dir)
    return snaps[0].path if snaps else None
