"""`plane observe`: scan the machine, write a snapshot (read-only)."""

from __future__ import annotations

import argparse

from planeops.cli.instance import instance_root


def _cmd(args: argparse.Namespace) -> int:
    from planeops.core.observe import run_observe
    from planeops.providers import ui

    repo = instance_root(args)
    snap = run_observe(repo, attest=args.attest)
    counts: dict[str, int] = {}
    for o in snap["observed"]:
        counts[o["adapter"]] = counts.get(o["adapter"], 0) + 1
    state = "ok" if not snap.get("failed") else "report"
    ui.headline(
        state,
        f"observed {len(snap['observed'])} facts on {snap['host']}",
        detail=str(repo / "observed" / snap["host"] / "snapshot.json"),
    )
    if counts:
        ui.breakdown(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    if snap["uncovered"]:
        ui.hint("uncovered adapters: " + ", ".join(sorted(snap["uncovered"])))
    # A crashed adapter produced no observations; silence here would let its
    # entries misreport downstream. Name it so the user sees the scan was partial.
    for f in snap.get("failed", []):
        ui.err(f"warning: adapter {f['adapter']!r} failed to scan: {f['error']}")
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "observe",
        help="scan the machine, write a snapshot (read-only)",
        description=(
            "Ask every discovered adapter what actually exists on this machine "
            "(services, packages, models, MCP wiring, secrets presence) and record "
            "it as observed/<host>/snapshot.json. Read-only with respect to the "
            "machine: it changes nothing, only records."
        ),
    )
    p.add_argument(
        "--attest", action="store_true", help="record fresh manual attestations"
    )
    p.set_defaults(func=_cmd)
