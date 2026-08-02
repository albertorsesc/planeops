"""`plane observe`: scan the machine, write a snapshot (read-only)."""

from __future__ import annotations

import argparse
import sys

from planeops.cli.instance import instance_root


def _cmd(args: argparse.Namespace) -> int:
    from planeops.core.observe import run_observe

    repo = instance_root(args)
    snap = run_observe(repo, attest=args.attest)
    print(
        f"observed {len(snap['observed'])} fact(s), "
        f"{len(snap['uncovered'])} uncovered adapter(s) "
        f"-> {repo / 'observed' / snap['host'] / 'snapshot.json'}"
    )
    # A crashed adapter produced no observations; silence here would let its
    # entries misreport downstream. Name it so the user sees the scan was partial.
    for f in snap.get("failed", []):
        print(
            f"warning: adapter {f['adapter']!r} failed to scan: {f['error']}",
            file=sys.stderr,
        )
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("observe", help="scan the machine, write a snapshot (read-only)")
    p.add_argument(
        "--attest", action="store_true", help="record fresh manual attestations"
    )
    p.set_defaults(func=_cmd)
