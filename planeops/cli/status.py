"""`plane status`: show the last drift report without recomputing (read-only)."""

from __future__ import annotations

import argparse
import json
import sys

from planeops.cli.instance import instance_root


def _cmd(args: argparse.Namespace) -> int:
    from planeops.core.status import read_status

    repo = instance_root(args)
    data = read_status(repo)  # last DRIFT.json, no recompute
    if data is None:
        if args.as_json:
            # --json is a machine contract: stdout always parses as JSON.
            print(json.dumps({"error": "no drift report yet; run `plane drift`"}))
        elif not args.short:  # a prompt wants silence, not an error, when unseeded
            print("no drift report yet; run `plane drift`", file=sys.stderr)
        return 0
    # A hand-edited or older-schema report may miss keys; the prompt path must
    # degrade, never traceback.
    alerts = data.get("alert_count", 0) or 0
    if args.as_json:
        print(json.dumps(data, indent=2))
    elif args.short:  # a shell-prompt token: nothing when clean
        if alerts:
            print(f"drift:{alerts}")
    else:
        summary = data.get("summary") or {}
        print(
            f"{alerts} alert(s), {summary.get('report', 0)} report, "
            f"{summary.get('uncovered', 0)} uncovered (as of {data.get('ts', '?')})"
        )
        # Resolution is invisible by design; the full status names which
        # instance answered so a wrong-instance reading is self-evident.
        print(f"instance: {repo}")
    return 2 if alerts else 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "status", help="show the last drift report without recomputing (read-only)"
    )
    p.add_argument(
        "--json", dest="as_json", action="store_true",
        help="emit the stored drift report as JSON",
    )  # fmt: skip
    p.add_argument(
        "--short", action="store_true",
        help="compact indicator for a shell prompt (prints nothing when clean)",
    )  # fmt: skip
    p.set_defaults(func=_cmd)
