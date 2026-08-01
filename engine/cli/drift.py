"""`plane drift`: diff desired vs observed, write DRIFT.md + DRIFT.json."""

from __future__ import annotations

import argparse
import json

from engine.cli.instance import instance_root


def _cmd(args: argparse.Namespace) -> int:
    from engine.core.drift import run_drift
    from engine.core.schema import SchemaError

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
        from engine.core.report import render_drift_json

        print(render_drift_json(report), end="")  # stdout is pure JSON, pipeable
    else:
        print(
            f"{report.alert_count} alert(s), {len(report.report)} report, "
            f"{len(report.uncovered)} uncovered -> observed/{report.host}/DRIFT.md"
        )
    return 2 if report.alert_count else 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "drift", help="diff desired vs observed, write DRIFT.md + DRIFT.json"
    )
    p.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print the drift report as JSON to stdout (for piping / MCP)",
    )
    p.set_defaults(func=_cmd)
