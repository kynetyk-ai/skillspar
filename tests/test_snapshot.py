"""Tests for snapshot save/load/list/find_latest."""

from __future__ import annotations

import json

import pytest

from skill_evaluator.reporting.snapshot import (
    SnapshotInfo,
    SnapshotLoadError,
    find_latest_snapshot,
    list_snapshots,
    load_snapshot,
    save_snapshot,
)


def _make_report(suite_name="My Suite", run_id="run-1", timestamp="2025-01-01T00:00:00+00:00"):
    return {
        "schema_version": "1",
        "suite": suite_name,
        "skill": "skill.md",
        "timestamp": timestamp,
        "run_id": run_id,
        "tests": [],
        "summary": {"total_tests": 0, "passed_tests": 0, "failed_tests": 0, "all_passed": True},
    }


class TestSaveSnapshot:
    def test_creates_file(self, tmp_path):
        report = _make_report()
        path = save_snapshot(report, snapshot_dir=tmp_path)
        assert path.exists()
        assert path.parent == tmp_path
        assert path.suffix == ".json"

    def test_filename_contains_slug(self, tmp_path):
        report = _make_report(suite_name="My Cool Suite")
        path = save_snapshot(report, snapshot_dir=tmp_path)
        assert "my-cool-suite" in path.name

    def test_creates_directory_if_missing(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        report = _make_report()
        path = save_snapshot(report, snapshot_dir=nested)
        assert path.exists()
        assert nested.exists()

    def test_written_content_matches_report(self, tmp_path):
        report = _make_report()
        path = save_snapshot(report, snapshot_dir=tmp_path)
        with open(path) as f:
            loaded = json.load(f)
        assert loaded == report


class TestLoadSnapshot:
    def test_loads_valid_snapshot(self, tmp_path):
        report = _make_report()
        path = tmp_path / "snap.json"
        with open(path, "w") as f:
            json.dump(report, f)

        loaded = load_snapshot(path)
        assert loaded == report

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(SnapshotLoadError, match="not found"):
            load_snapshot(tmp_path / "nonexistent.json")

    def test_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json at all")
        with pytest.raises(SnapshotLoadError, match="Failed to read"):
            load_snapshot(path)

    def test_raises_on_missing_schema_version(self, tmp_path):
        path = tmp_path / "no_version.json"
        with open(path, "w") as f:
            json.dump({"suite": "test"}, f)
        with pytest.raises(SnapshotLoadError, match="schema_version"):
            load_snapshot(path)

    def test_raises_on_non_object(self, tmp_path):
        path = tmp_path / "array.json"
        with open(path, "w") as f:
            json.dump([1, 2, 3], f)
        with pytest.raises(SnapshotLoadError, match="not a JSON object"):
            load_snapshot(path)


class TestListSnapshots:
    def test_returns_empty_for_missing_dir(self, tmp_path):
        result = list_snapshots(snapshot_dir=tmp_path / "nonexistent")
        assert result == []

    def test_lists_all_snapshots(self, tmp_path):
        # Write files directly with distinct names to avoid timestamp collision
        for i in range(3):
            report = _make_report(suite_name="suite", timestamp=f"2025-01-0{i+1}T00:00:00+00:00")
            path = tmp_path / f"suite_2025010{i+1}-000000.json"
            import json
            with open(path, "w") as f:
                json.dump(report, f)
        result = list_snapshots(snapshot_dir=tmp_path)
        assert len(result) == 3
        # Newest first
        assert result[0].timestamp > result[-1].timestamp

    def test_filters_by_suite_name(self, tmp_path):
        save_snapshot(_make_report(suite_name="alpha"), snapshot_dir=tmp_path)
        save_snapshot(_make_report(suite_name="beta"), snapshot_dir=tmp_path)

        alpha_snaps = list_snapshots(suite_name="alpha", snapshot_dir=tmp_path)
        assert len(alpha_snaps) == 1
        assert alpha_snaps[0].suite_name == "alpha"

    def test_skips_malformed_files(self, tmp_path):
        save_snapshot(_make_report(), snapshot_dir=tmp_path)
        # Write a bad file
        (tmp_path / "bad.json").write_text("not json")
        result = list_snapshots(snapshot_dir=tmp_path)
        assert len(result) == 1

    def test_snapshot_info_fields(self, tmp_path):
        report = _make_report(suite_name="Test", run_id="abc-123", timestamp="2025-06-15T12:00:00+00:00")
        save_snapshot(report, snapshot_dir=tmp_path)
        snaps = list_snapshots(snapshot_dir=tmp_path)
        assert len(snaps) == 1
        info = snaps[0]
        assert isinstance(info, SnapshotInfo)
        assert info.suite_name == "Test"
        assert info.run_id == "abc-123"
        assert info.timestamp == "2025-06-15T12:00:00+00:00"


class TestFindLatestSnapshot:
    def test_returns_none_when_empty(self, tmp_path):
        result = find_latest_snapshot("no-suite", snapshot_dir=tmp_path)
        assert result is None

    def test_returns_latest(self, tmp_path):
        save_snapshot(
            _make_report(suite_name="s", timestamp="2025-01-01T00:00:00+00:00"),
            snapshot_dir=tmp_path,
        )
        save_snapshot(
            _make_report(suite_name="s", timestamp="2025-06-01T00:00:00+00:00"),
            snapshot_dir=tmp_path,
        )
        result = find_latest_snapshot("s", snapshot_dir=tmp_path)
        assert result is not None
        data = load_snapshot(result)
        assert data["timestamp"] == "2025-06-01T00:00:00+00:00"

    def test_ignores_other_suites(self, tmp_path):
        save_snapshot(_make_report(suite_name="other"), snapshot_dir=tmp_path)
        result = find_latest_snapshot("target", snapshot_dir=tmp_path)
        assert result is None
