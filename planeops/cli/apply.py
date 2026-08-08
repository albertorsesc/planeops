"""`plane apply`: converge confirmed changes, one at a time."""

from __future__ import annotations

import argparse

from planeops.cli.instance import instance_root


def _cmd(args: argparse.Namespace) -> int:
    from planeops.core.apply import run_apply
    from planeops.providers import ui

    repo = instance_root(args)
    applied = run_apply(repo, only_id=args.id, only_phase=args.phase)

    if not applied:
        from planeops.core.status import read_status

        # "planned nothing" is NOT "no drift": a service file not yet on disk, an
        # uncovered adapter, or an owner: human entry all plan [] while drift
        # alerts. Say so instead of claiming the machine matches desired state.
        ui.line("no changes planned from the last snapshot")
        data = read_status(repo)
        alerts = data.get("alert_count", 0) if data else 0
        if alerts:
            ui.warn(
                f"note: drift still reports {alerts} alert(s); a gap may need a "
                "hand first (a service file not on disk, an uncovered adapter, an "
                "owner: human entry), or a fresh `plane observe`"
            )
        return 0

    executed = [a for a in applied if a.executed]
    skipped = [a for a in applied if not a.executed]
    failed = [a for a in executed if not (a.result and a.result.ok)]
    width = min(max(len(a.change.entry_id) for a in executed), 40) if executed else 0
    for a in executed:
        detail = a.result.detail if a.result else ""
        state = "ok" if (a.result and a.result.ok) else "alert"
        ui.item(state, a.change.entry_id, detail, width)
    summary = f"{len(executed)} applied ({len(failed)} failed), {len(skipped)} skipped"
    ui.headline("alert" if failed else "ok", summary)
    if executed:
        from planeops.core.drift import run_drift
        from planeops.core.observe import run_observe

        # Re-observe AND recompute the drift panes, so `plane status` (and a shell
        # prompt reading DRIFT.json) reflects this apply now, not at the next
        # scheduled reconcile.
        run_observe(repo)
        report = run_drift(repo)
        head = (
            f"{report.alert_count} alert(s), {len(report.report)} report, "
            f"{len(report.uncovered)} uncovered"
        )
        detail = f"-> {repo / 'observed' / report.host / 'DRIFT.md'}"
        ui.warn(head, detail) if report.alert_count else ui.good(head, detail)
    return 1 if failed else 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "apply",
        help="converge confirmed changes, one at a time",
        description=(
            "The only verb that changes the machine. Plans changes from the last "
            "snapshot, renders each as a diff, and asks before every single one: "
            "y applies it, n skips it, a approves the rest of that domain for "
            "this run only. Nothing is ever auto-approved, and a successful "
            "apply re-observes so status reflects it immediately."
        ),
    )
    p.add_argument("--id", default=None, help="apply only the entry with this id")
    p.add_argument(
        "--phase",
        type=int,
        default=None,
        help="apply only entries in this converge phase",
    )
    p.set_defaults(func=_cmd)
