"""Tests for the diff engine."""

from __future__ import annotations

from skill_evaluator.reporting.diff import diff_snapshots


def _make_snapshot(
    tests=None,
    timestamp="2025-01-01T00:00:00+00:00",
    run_id="run-1",
    skill_file_hash="abc123",
):
    return {
        "schema_version": "1",
        "suite": "test-suite",
        "timestamp": timestamp,
        "run_id": run_id,
        "skill_file_hash": skill_file_hash,
        "tests": tests or [],
        "summary": {},
    }


def _make_test(
    name="test-1",
    pass_rate=1.0,
    passed=True,
    baseline_summary=None,
    runs=None,
):
    t = {
        "name": name,
        "summary": {"pass_rate": pass_rate, "passed": passed},
        "runs": runs or [{"assertions": []}],
    }
    if baseline_summary is not None:
        t["baseline_summary"] = baseline_summary
    return t


class TestIdenticalSnapshots:
    def test_no_changes(self):
        snap = _make_snapshot(tests=[_make_test()])
        diff = diff_snapshots(snap, snap)
        assert diff.summary.regressions == 0
        assert diff.summary.improvements == 0
        assert diff.summary.steer_erosions == 0
        assert diff.summary.unchanged == 1
        assert diff.added_tests == []
        assert diff.removed_tests == []

    def test_skill_hash_unchanged(self):
        snap = _make_snapshot(skill_file_hash="same")
        diff = diff_snapshots(snap, snap)
        assert diff.skill_hash_changed is False


class TestPassRateRegression:
    def test_detects_regression(self):
        before = _make_snapshot(tests=[_make_test(pass_rate=1.0, passed=True)])
        after = _make_snapshot(tests=[_make_test(pass_rate=0.5, passed=False)])
        diff = diff_snapshots(before, after)
        assert diff.summary.regressions == 1
        assert diff.test_diffs[0].pass_rate_delta < 0
        assert diff.test_diffs[0].status_changed is True


class TestPassRateImprovement:
    def test_detects_improvement(self):
        before = _make_snapshot(tests=[_make_test(pass_rate=0.5, passed=False)])
        after = _make_snapshot(tests=[_make_test(pass_rate=1.0, passed=True)])
        diff = diff_snapshots(before, after)
        assert diff.summary.improvements == 1
        assert diff.test_diffs[0].pass_rate_delta > 0


class TestSteerErosion:
    def test_detects_erosion(self):
        before = _make_snapshot(tests=[
            _make_test(baseline_summary={"pass_rate": 0.2}),
        ])
        after = _make_snapshot(tests=[
            _make_test(baseline_summary={"pass_rate": 0.8}),
        ])
        diff = diff_snapshots(before, after)
        assert diff.summary.steer_erosions == 1
        assert diff.test_diffs[0].steer_eroded is True
        assert diff.test_diffs[0].baseline_pass_rate_before == 0.2
        assert diff.test_diffs[0].baseline_pass_rate_after == 0.8

    def test_no_erosion_when_baseline_drops(self):
        before = _make_snapshot(tests=[
            _make_test(baseline_summary={"pass_rate": 0.8}),
        ])
        after = _make_snapshot(tests=[
            _make_test(baseline_summary={"pass_rate": 0.3}),
        ])
        diff = diff_snapshots(before, after)
        assert diff.summary.steer_erosions == 0
        assert diff.test_diffs[0].steer_eroded is False

    def test_no_erosion_without_baseline(self):
        before = _make_snapshot(tests=[_make_test()])
        after = _make_snapshot(tests=[_make_test()])
        diff = diff_snapshots(before, after)
        assert diff.summary.steer_erosions == 0


class TestAddedRemovedTests:
    def test_added_tests(self):
        before = _make_snapshot(tests=[])
        after = _make_snapshot(tests=[_make_test(name="new-test")])
        diff = diff_snapshots(before, after)
        assert diff.added_tests == ["new-test"]
        assert diff.removed_tests == []

    def test_removed_tests(self):
        before = _make_snapshot(tests=[_make_test(name="old-test")])
        after = _make_snapshot(tests=[])
        diff = diff_snapshots(before, after)
        assert diff.removed_tests == ["old-test"]
        assert diff.added_tests == []

    def test_mixed_added_and_removed(self):
        before = _make_snapshot(tests=[_make_test(name="a"), _make_test(name="b")])
        after = _make_snapshot(tests=[_make_test(name="b"), _make_test(name="c")])
        diff = diff_snapshots(before, after)
        assert diff.added_tests == ["c"]
        assert diff.removed_tests == ["a"]
        # "b" is common — should appear in test_diffs
        assert len(diff.test_diffs) == 1
        assert diff.test_diffs[0].test_name == "b"


class TestAssertionFlips:
    def test_detects_assertion_flip(self):
        before_runs = [{"assertions": [
            {"type": "output_contains", "status": "passed", "details": {"substring": "hello"}},
        ]}]
        after_runs = [{"assertions": [
            {"type": "output_contains", "status": "failed", "details": {"substring": "hello"}},
        ]}]
        before = _make_snapshot(tests=[_make_test(runs=before_runs)])
        after = _make_snapshot(tests=[_make_test(runs=after_runs)])
        diff = diff_snapshots(before, after)
        assert len(diff.test_diffs[0].assertion_flips) == 1
        flip = diff.test_diffs[0].assertion_flips[0]
        assert flip.before_status == "passed"
        assert flip.after_status == "failed"
        assert flip.assertion_type == "output_contains"

    def test_no_flips_when_same(self):
        runs = [{"assertions": [
            {"type": "output_contains", "status": "passed", "details": {"substring": "hello"}},
        ]}]
        snap = _make_snapshot(tests=[_make_test(runs=runs)])
        diff = diff_snapshots(snap, snap)
        assert diff.test_diffs[0].assertion_flips == []


class TestSkillHashChange:
    def test_detects_hash_change(self):
        before = _make_snapshot(skill_file_hash="abc")
        after = _make_snapshot(skill_file_hash="xyz")
        diff = diff_snapshots(before, after)
        assert diff.skill_hash_changed is True

    def test_no_change_when_hashes_match(self):
        snap = _make_snapshot(skill_file_hash="same")
        diff = diff_snapshots(snap, snap)
        assert diff.skill_hash_changed is False

    def test_no_change_when_hashes_missing(self):
        before = _make_snapshot()
        before.pop("skill_file_hash", None)
        after = _make_snapshot()
        after.pop("skill_file_hash", None)
        diff = diff_snapshots(before, after)
        assert diff.skill_hash_changed is False


class TestMetadata:
    def test_run_ids_and_timestamps(self):
        before = _make_snapshot(run_id="r1", timestamp="2025-01-01T00:00:00")
        after = _make_snapshot(run_id="r2", timestamp="2025-06-01T00:00:00")
        diff = diff_snapshots(before, after)
        assert diff.before_run_id == "r1"
        assert diff.after_run_id == "r2"
        assert diff.before_timestamp == "2025-01-01T00:00:00"
        assert diff.after_timestamp == "2025-06-01T00:00:00"

    def test_multiple_tests_summary(self):
        before = _make_snapshot(tests=[
            _make_test(name="a", pass_rate=1.0),
            _make_test(name="b", pass_rate=0.5),
            _make_test(name="c", pass_rate=0.8),
        ])
        after = _make_snapshot(tests=[
            _make_test(name="a", pass_rate=0.5),   # regression
            _make_test(name="b", pass_rate=1.0),   # improvement
            _make_test(name="c", pass_rate=0.8),   # unchanged
        ])
        diff = diff_snapshots(before, after)
        assert diff.summary.total_tests == 3
        assert diff.summary.regressions == 1
        assert diff.summary.improvements == 1
        assert diff.summary.unchanged == 1
