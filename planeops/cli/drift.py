"""`plane drift`: diff desired vs observed, write DRIFT.md + DRIFT.json."""

from __future__ import annotations

import argparse
import json

from planeops.cli.instance import instance_root


def _cmd(args: argparse.Namespace) -> int:
    from planeops.core.drift import run_drift
    from planeops.core.schema import SchemaError

    repo = instance_root(args)
    try:
        report = run_drift(repo)
    except (FileNotFoundError, SchemaError) as exc:
        if args.as_json:
            # --json is a machine contract: stdout parses as JSON even on an
            # operator error; the exit code still carries the verdict.
            print(json.dumps({"error": str(exc)}))
            return 1
        raise  # text mode: the central handler prints it
    if args.as_json:
        from planeops.core.report import render_drift_json

        print(render_drift_json(report), end="")  # stdout is pure JSON, pipeable
    else:
        _render(report, repo)
    return 2 if report.alert_count else 0


# Sections over this size truncate on screen: the terminal view is triage,
# DRIFT.md is the archive.
_SECTION_CAP = 15


def _render(report, repo) -> None:  # type: ignore[no-untyped-def]
    from planeops.cli._text import human_ts
    from planeops.providers import ui

    quiet = not (
        report.alerts
        or report.report
        or report.uncovered
        or report.ungoverned
        or report.reauth
    )
    if quiet:
        ui.headline("ok", f"no drift on {report.host}", detail=human_ts(report.ts))
        return

    state = "alert" if report.alert_count else "report"
    ui.headline(
        state,
        f"{report.alert_count} alert(s) on {report.host}",
        detail=human_ts(report.ts),
    )

    def sec(name: str, items: list, item_state: str) -> None:  # type: ignore[type-arg]
        if not items:
            return
        ui.section(name, len(items))
        width = min(max(len(i.entry_id) for i in items), 40)
        messages = {i.message for i in items}
        if len(items) > 1 and len(messages) == 1:
            # Every item says the same thing: say it once, list the ids.
            for i in items[:_SECTION_CAP]:
                ui.item(item_state, i.entry_id, "", width)
            ui.hint(messages.pop())
        else:
            for i in items[:_SECTION_CAP]:
                ui.item(item_state, i.entry_id, i.message, width)
        if len(items) > _SECTION_CAP:
            ui.hint(f"... and {len(items) - _SECTION_CAP} more (see DRIFT.md)")

    sec("alerts", report.alerts, "alert")
    sec("reports", report.report, "report")
    sec("uncovered", report.uncovered, "unknown")
    sec("ungoverned", report.ungoverned, "unknown")
    sec("re-auth pending", report.reauth, "neutral")
    ui.line()
    ui.hint(f"full report {repo / 'observed' / report.host / 'DRIFT.md'}")


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "drift",
        help="diff desired vs observed, write DRIFT.md + DRIFT.json",
        description=(
            "Compare the registry (desired state) against the last snapshot and "
            "triage the differences: alerts (lifecycle violations, missing "
            "requirements), reports (worth a look), auto-folded noise, and "
            "ungoverned items nobody declared. Writes DRIFT.md for you and "
            "DRIFT.json for machines. Exit code 2 means alerts exist."
        ),
    )
    p.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print the drift report as JSON to stdout (for piping / MCP)",
    )
    p.set_defaults(func=_cmd)
