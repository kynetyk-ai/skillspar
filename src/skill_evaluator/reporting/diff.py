"""Diff engine — compare two snapshot dicts and produce a structured delta."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AssertionFlip:
    """A single assertion whose status changed between snapshots."""

    assertion_type: str
    before_status: str
    after_status: str
    message: str


@dataclass
class TestDiff:
    """Delta for a single test between two snapshots."""

    __test__ = False

    test_name: str
    pass_rate_before: float
    pass_rate_after: float
    pass_rate_delta: float
    status_changed: bool
    baseline_pass_rate_before: float | None = None
    baseline_pass_rate_after: float | None = None
    steer_eroded: bool = False
    assertion_flips: list[AssertionFlip] = field(default_factory=list)


@dataclass
class DiffSummary:
    """Aggregate counts for the diff."""

    total_tests: int
    regressions: int
    improvements: int
    steer_erosions: int
    unchanged: int


@dataclass
class SnapshotDiff:
    """Full diff between two snapshots."""

    before_run_id: str | None
    after_run_id: str | None
    before_timestamp: str
    after_timestamp: str
    skill_hash_changed: bool
    test_diffs: list[TestDiff] = field(default_factory=list)
    added_tests: list[str] = field(default_factory=list)
    removed_tests: list[str] = field(default_factory=list)
    summary: DiffSummary = field(default_factory=lambda: DiffSummary(0, 0, 0, 0, 0))


def _build_test_index(snapshot: dict) -> dict[str, dict]:
    """Index tests by name for O(1) lookup."""
    return {t["name"]: t for t in snapshot.get("tests", [])}


def _assertion_key(assertion: dict) -> str:
    """Best-effort key for matching assertions across snapshots."""
    atype = assertion.get("type", "")
    details = assertion.get("details") or {}
    # Use common identifying fields from details
    parts = [atype]
    for k in ("tool_name", "value", "pattern", "expected", "substring"):
        if k in details:
            parts.append(str(details[k]))
    return "|".join(parts)


def _diff_assertions(before_runs: list[dict], after_runs: list[dict]) -> list[AssertionFlip]:
    """Compare assertion outcomes between before/after runs (best-effort).

    Uses the first run from each snapshot for assertion-level comparison.
    """
    if not before_runs or not after_runs:
        return []

    before_assertions = before_runs[0].get("assertions", [])
    after_assertions = after_runs[0].get("assertions", [])

    before_by_key = {_assertion_key(a): a for a in before_assertions}
    after_by_key = {_assertion_key(a): a for a in after_assertions}

    flips = []
    for key, before_a in before_by_key.items():
        after_a = after_by_key.get(key)
        if after_a is None:
            continue
        b_status = before_a.get("status", "")
        a_status = after_a.get("status", "")
        if b_status != a_status:
            flips.append(
                AssertionFlip(
                    assertion_type=before_a.get("type", ""),
                    before_status=b_status,
                    after_status=a_status,
                    message=f"{before_a.get('type', '')} {b_status} -> {a_status}",
                )
            )
    return flips


def diff_snapshots(before: dict, after: dict) -> SnapshotDiff:
    """Compare two snapshot dicts and produce a structured delta."""
    before_tests = _build_test_index(before)
    after_tests = _build_test_index(after)

    before_names = set(before_tests.keys())
    after_names = set(after_tests.keys())

    added = sorted(after_names - before_names)
    removed = sorted(before_names - after_names)
    common = sorted(before_names & after_names)

    # Detect skill hash change
    before_hash = before.get("skill_file_hash")
    after_hash = after.get("skill_file_hash")
    skill_hash_changed = (
        before_hash is not None and after_hash is not None and before_hash != after_hash
    )

    test_diffs: list[TestDiff] = []
    regressions = 0
    improvements = 0
    steer_erosions = 0
    unchanged = 0

    for name in common:
        bt = before_tests[name]
        at = after_tests[name]

        b_summary = bt.get("summary", {})
        a_summary = at.get("summary", {})

        b_rate = b_summary.get("pass_rate", 0.0)
        a_rate = a_summary.get("pass_rate", 0.0)
        delta = a_rate - b_rate

        b_passed = b_summary.get("passed", False)
        a_passed = a_summary.get("passed", False)
        status_changed = b_passed != a_passed

        # Baseline pass rates
        b_bl = bt.get("baseline_summary")
        a_bl = at.get("baseline_summary")
        b_bl_rate = b_bl.get("pass_rate") if b_bl else None
        a_bl_rate = a_bl.get("pass_rate") if a_bl else None

        # Steer erosion: baseline pass rate rose
        steer_eroded = b_bl_rate is not None and a_bl_rate is not None and a_bl_rate > b_bl_rate

        # Assertion flips
        flips = _diff_assertions(
            bt.get("runs", []),
            at.get("runs", []),
        )

        td = TestDiff(
            test_name=name,
            pass_rate_before=b_rate,
            pass_rate_after=a_rate,
            pass_rate_delta=delta,
            status_changed=status_changed,
            baseline_pass_rate_before=b_bl_rate,
            baseline_pass_rate_after=a_bl_rate,
            steer_eroded=steer_eroded,
            assertion_flips=flips,
        )
        test_diffs.append(td)

        if delta < 0:
            regressions += 1
        elif delta > 0:
            improvements += 1
        else:
            unchanged += 1

        if steer_eroded:
            steer_erosions += 1

    summary = DiffSummary(
        total_tests=len(common),
        regressions=regressions,
        improvements=improvements,
        steer_erosions=steer_erosions,
        unchanged=unchanged,
    )

    return SnapshotDiff(
        before_run_id=before.get("run_id"),
        after_run_id=after.get("run_id"),
        before_timestamp=before.get("timestamp", ""),
        after_timestamp=after.get("timestamp", ""),
        skill_hash_changed=skill_hash_changed,
        test_diffs=test_diffs,
        added_tests=added,
        removed_tests=removed,
        summary=summary,
    )
