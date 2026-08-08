"""`plane reconcile`: observe then drift in one pass (for a scheduler)."""

from __future__ import annotations

import argparse

from planeops.cli.instance import instance_root


def _cmd(args: argparse.Namespace) -> int:
    from planeops.core.drift import run_drift
    from planeops.core.observe import run_observe
    from planeops.providers import ui

    repo = instance_root(args)
    snap = run_observe(repo)  # scan + write the snapshot
    ui.line(
        f"observed {len(snap['observed'])} fact(s)",
        detail=f"-> {repo / 'observed' / snap['host'] / 'snapshot.json'}",
    )
    report = run_drift(repo)  # diff the fresh snapshot, write DRIFT.md + DRIFT.json
    head = (
        f"{report.alert_count} alert(s), {len(report.report)} report, "
        f"{len(report.uncovered)} uncovered"
    )
    detail = f"-> {repo / 'observed' / report.host / 'DRIFT.md'}"
    ui.warn(head, detail) if report.alert_count else ui.good(head, detail)
    return 2 if report.alert_count else 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "reconcile",
        help="observe then drift in one pass (for a scheduler)",
        description=(
            "observe followed by drift as one command: scan the machine, then "
            "triage against the registry. Made for the ambient timer that "
            "`plane schedule` sets up; run it by hand for a one-shot refresh. "
            "Exit code 2 means alerts exist."
        ),
    )
    p.set_defaults(func=_cmd)
