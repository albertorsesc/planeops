"""`plane reconcile`: observe then drift in one pass (for a scheduler)."""

from __future__ import annotations

import argparse

from planeops.cli.instance import instance_root


def _cmd(args: argparse.Namespace) -> int:
    from planeops.core.drift import run_drift
    from planeops.core.observe import run_observe

    repo = instance_root(args)
    snap = run_observe(repo)  # scan + write the snapshot
    print(
        f"observed {len(snap['observed'])} fact(s) "
        f"-> {repo / 'observed' / snap['host'] / 'snapshot.json'}"
    )
    report = run_drift(repo)  # diff the fresh snapshot, write DRIFT.md + DRIFT.json
    print(
        f"{report.alert_count} alert(s), {len(report.report)} report, "
        f"{len(report.uncovered)} uncovered "
        f"-> {repo / 'observed' / report.host / 'DRIFT.md'}"
    )
    return 2 if report.alert_count else 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "reconcile", help="observe then drift in one pass (for a scheduler)"
    )
    p.set_defaults(func=_cmd)
