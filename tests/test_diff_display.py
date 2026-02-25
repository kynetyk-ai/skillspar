"""Tests for diff display rendering."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from skill_evaluator.reporting.diff import (
    AssertionFlip,
    DiffSummary,
    SnapshotDiff,
    TestDiff,
)
from skill_evaluator.reporting.diff_display import display_diff


def _make_console():
    buf = StringIO()
    return Console(file=buf, no_color=True, width=120), buf


class TestDisplayDiff:
    def test_renders_without_error(self):
        console, buf = _make_console()
        diff = SnapshotDiff(
            before_run_id="r1",
            after_run_id="r2",
            before_timestamp="2025-01-01T00:00:00",
            after_timestamp="2025-06-01T00:00:00",
            skill_hash_changed=False,
            test_diffs=[
                TestDiff(
                    test_name="test-1",
                    pass_rate_before=1.0,
                    pass_rate_after=0.5,
                    pass_rate_delta=-0.5,
                    status_changed=True,
                ),
            ],
            summary=DiffSummary(total_tests=1, regressions=1, improvements=0, steer_erosions=0, unchanged=0),
        )
        display_diff(diff, console=console)
        output = buf.getvalue()
        assert "test-1" in output
        assert "REGRESSION" in output

    def test_shows_improvement(self):
        console, buf = _make_console()
        diff = SnapshotDiff(
            before_run_id=None,
            after_run_id=None,
            before_timestamp="t1",
            after_timestamp="t2",
            skill_hash_changed=False,
            test_diffs=[
                TestDiff(
                    test_name="improved-test",
                    pass_rate_before=0.5,
                    pass_rate_after=1.0,
                    pass_rate_delta=0.5,
                    status_changed=True,
                ),
            ],
            summary=DiffSummary(total_tests=1, regressions=0, improvements=1, steer_erosions=0, unchanged=0),
        )
        display_diff(diff, console=console)
        output = buf.getvalue()
        assert "IMPROVED" in output

    def test_shows_steer_erosion(self):
        console, buf = _make_console()
        diff = SnapshotDiff(
            before_run_id=None,
            after_run_id=None,
            before_timestamp="t1",
            after_timestamp="t2",
            skill_hash_changed=False,
            test_diffs=[
                TestDiff(
                    test_name="eroded-test",
                    pass_rate_before=1.0,
                    pass_rate_after=1.0,
                    pass_rate_delta=0.0,
                    status_changed=False,
                    baseline_pass_rate_before=0.2,
                    baseline_pass_rate_after=0.8,
                    steer_eroded=True,
                ),
            ],
            summary=DiffSummary(total_tests=1, regressions=0, improvements=0, steer_erosions=1, unchanged=0),
        )
        display_diff(diff, console=console)
        output = buf.getvalue()
        assert "EROSION" in output
        assert "baseline" in output

    def test_shows_skill_hash_warning(self):
        console, buf = _make_console()
        diff = SnapshotDiff(
            before_run_id=None,
            after_run_id=None,
            before_timestamp="t1",
            after_timestamp="t2",
            skill_hash_changed=True,
            summary=DiffSummary(total_tests=0, regressions=0, improvements=0, steer_erosions=0, unchanged=0),
        )
        display_diff(diff, console=console)
        output = buf.getvalue()
        assert "skill file hash changed" in output

    def test_shows_added_removed_tests(self):
        console, buf = _make_console()
        diff = SnapshotDiff(
            before_run_id=None,
            after_run_id=None,
            before_timestamp="t1",
            after_timestamp="t2",
            skill_hash_changed=False,
            added_tests=["new-test"],
            removed_tests=["old-test"],
            summary=DiffSummary(total_tests=0, regressions=0, improvements=0, steer_erosions=0, unchanged=0),
        )
        display_diff(diff, console=console)
        output = buf.getvalue()
        assert "new-test" in output
        assert "old-test" in output
        assert "Added" in output
        assert "Removed" in output

    def test_shows_assertion_flips(self):
        console, buf = _make_console()
        diff = SnapshotDiff(
            before_run_id=None,
            after_run_id=None,
            before_timestamp="t1",
            after_timestamp="t2",
            skill_hash_changed=False,
            test_diffs=[
                TestDiff(
                    test_name="flip-test",
                    pass_rate_before=1.0,
                    pass_rate_after=0.0,
                    pass_rate_delta=-1.0,
                    status_changed=True,
                    assertion_flips=[
                        AssertionFlip(
                            assertion_type="output_contains",
                            before_status="passed",
                            after_status="failed",
                            message="output_contains passed -> failed",
                        ),
                    ],
                ),
            ],
            summary=DiffSummary(total_tests=1, regressions=1, improvements=0, steer_erosions=0, unchanged=0),
        )
        display_diff(diff, console=console)
        output = buf.getvalue()
        assert "output_contains" in output
        assert "passed" in output
        assert "failed" in output

    def test_summary_line(self):
        console, buf = _make_console()
        diff = SnapshotDiff(
            before_run_id=None,
            after_run_id=None,
            before_timestamp="t1",
            after_timestamp="t2",
            skill_hash_changed=False,
            test_diffs=[
                TestDiff("a", 1.0, 0.5, -0.5, True),
                TestDiff("b", 0.5, 1.0, 0.5, True),
            ],
            summary=DiffSummary(total_tests=2, regressions=1, improvements=1, steer_erosions=0, unchanged=0),
        )
        display_diff(diff, console=console)
        output = buf.getvalue()
        assert "1 regression" in output
        assert "1 improvement" in output

    def test_empty_diff(self):
        console, buf = _make_console()
        diff = SnapshotDiff(
            before_run_id=None,
            after_run_id=None,
            before_timestamp="t1",
            after_timestamp="t2",
            skill_hash_changed=False,
            summary=DiffSummary(total_tests=0, regressions=0, improvements=0, steer_erosions=0, unchanged=0),
        )
        display_diff(diff, console=console)
        output = buf.getvalue()
        assert "No comparable tests" in output
