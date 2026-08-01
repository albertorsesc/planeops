"""`plane apply`: converge confirmed changes, one at a time."""

from __future__ import annotations

import argparse

from engine.cli.instance import instance_root


def _cmd(args: argparse.Namespace) -> int:
    from engine.core.apply import run_apply

    repo = instance_root(args)
    applied = run_apply(repo, only_id=args.id, only_phase=args.phase)

    if not applied:
        from engine.core.status import read_status

        # "planned nothing" is NOT "no drift": a service file not yet on disk, an
        # uncovered adapter, or an owner: human entry all plan [] while drift
        # alerts. Say so instead of claiming the machine matches desired state.
        print("no changes planned from the last snapshot")
        data = read_status(repo)
        alerts = data.get("alert_count", 0) if data else 0
        if alerts:
            print(
                f"note: drift still reports {alerts} alert(s); a gap may need a "
                "hand first (a service file not on disk, an uncovered adapter, an "
                "owner: human entry), or a fresh `plane observe`"
            )
        return 0

    executed = [a for a in applied if a.executed]
    skipped = [a for a in applied if not a.executed]
    failed = [a for a in executed if not (a.result and a.result.ok)]
    for a in executed:
        status = "ok" if (a.result and a.result.ok) else "FAILED"
        print(
            f"  [{status}] {a.change.entry_id}: {a.result.detail if a.result else ''}"
        )
    print(f"{len(executed)} applied ({len(failed)} failed), {len(skipped)} skipped")
    if executed:
        from engine.core.drift import run_drift
        from engine.core.observe import run_observe

        # Re-observe AND recompute the drift panes, so `plane status` (and a shell
        # prompt reading DRIFT.json) reflects this apply now, not at the next
        # scheduled reconcile.
        run_observe(repo)
        report = run_drift(repo)
        print(
            f"{report.alert_count} alert(s), {len(report.report)} report, "
            f"{len(report.uncovered)} uncovered -> observed/{report.host}/DRIFT.md"
        )
    return 1 if failed else 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("apply", help="converge confirmed changes, one at a time")
    p.add_argument("--id", default=None, help="apply only the entry with this id")
    p.add_argument(
        "--phase",
        type=int,
        default=None,
        help="apply only entries in this converge phase",
    )
    p.set_defaults(func=_cmd)
