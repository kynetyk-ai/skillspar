"""Rich console display for snapshot diffs."""

from __future__ import annotations

from rich.console import Console

from skill_evaluator.reporting.diff import SnapshotDiff


def display_diff(diff: SnapshotDiff, console: Console | None = None) -> None:
    """Render a SnapshotDiff to the terminal using Rich."""
    console = console or Console()

    # Header
    console.print()
    console.print(
        f"[bold]Diff:[/bold] {diff.before_timestamp} -> {diff.after_timestamp}"
    )
    if diff.skill_hash_changed:
        console.print("[yellow]Warning: skill file hash changed between snapshots[/yellow]")
    console.print()

    # Per-test rows
    for td in diff.test_diffs:
        before_pct = f"{td.pass_rate_before:.0%}"
        after_pct = f"{td.pass_rate_after:.0%}"

        if td.pass_rate_delta < 0:
            label = "[red]REGRESSION[/red]"
        elif td.pass_rate_delta > 0:
            label = "[green]IMPROVED[/green]"
        elif td.steer_eroded:
            label = "[yellow]EROSION[/yellow]"
        else:
            label = "[dim]--[/dim]"

        line = f"  {td.test_name}  {before_pct} -> {after_pct}  {label}"

        if td.pass_rate_delta < 0:
            console.print(f"[red]{line}[/red]")
        elif td.pass_rate_delta > 0:
            console.print(f"[green]{line}[/green]")
        elif td.steer_eroded:
            console.print(f"[yellow]{line}[/yellow]")
        else:
            console.print(f"[dim]{line}[/dim]")

        # Steer erosion detail
        if td.steer_eroded:
            console.print(
                f"    [yellow]baseline: {td.baseline_pass_rate_before:.0%} -> "
                f"{td.baseline_pass_rate_after:.0%}[/yellow]"
            )

        # Assertion flips
        for flip in td.assertion_flips:
            console.print(
                f"    [dim]{flip.assertion_type}: "
                f"{flip.before_status} -> {flip.after_status}[/dim]"
            )

    # Added / removed tests
    if diff.added_tests:
        console.print()
        console.print("[green]Added tests:[/green]")
        for name in diff.added_tests:
            console.print(f"  + {name}")

    if diff.removed_tests:
        console.print()
        console.print("[red]Removed tests:[/red]")
        for name in diff.removed_tests:
            console.print(f"  - {name}")

    # Summary line
    console.print()
    s = diff.summary
    parts = []
    if s.regressions:
        parts.append(f"[red]{s.regressions} regression{'s' if s.regressions != 1 else ''}[/red]")
    if s.improvements:
        parts.append(f"[green]{s.improvements} improvement{'s' if s.improvements != 1 else ''}[/green]")
    if s.steer_erosions:
        parts.append(f"[yellow]{s.steer_erosions} steer erosion{'s' if s.steer_erosions != 1 else ''}[/yellow]")
    if s.unchanged:
        parts.append(f"{s.unchanged} unchanged")

    if parts:
        console.print(", ".join(parts))
    else:
        console.print("[dim]No comparable tests[/dim]")
