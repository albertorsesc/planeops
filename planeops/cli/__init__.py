"""`plane` CLI: pure composition. Each verb lives in its own module owning both
its command and its parser registration; this package assembles them, dispatches,
and handles the expected operator errors in exactly one place.

Verbs: init, observe, drift, reconcile, schedule, apply, import, status, mcp.
observe, drift, status, and mcp are read-only; reconcile is observe+drift in one
pass (for a scheduler); schedule previews, confirms, then writes the OS
reconcile-timer files + a registry entry (apply loads it); init scaffolds an
instance + the home config pointer. apply renders a diff and requires
confirmation before each mutation; the engine owns that gate, not the adapters.
"""

from __future__ import annotations

import argparse
import sys
from typing import cast

from planeops import __version__
from planeops.cli import (
    apply,
    drift,
    import_,
    init,
    mcp,
    observe,
    reconcile,
    schedule,
    status,
)

# Registration order = `plane --help` order: the loop verbs first, then setup.
# Journey order, not implementation order: --help doubles as the getting-started
# path (init first, then the daily loop, then the occasional verbs).
_VERBS = (init, observe, drift, status, apply, reconcile, schedule, import_, mcp)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plane", description="personal AI control plane"
    )
    parser.add_argument("--version", action="version", version=f"plane {__version__}")
    parser.add_argument(
        "--repo",
        default=None,
        help="instance root; else $PLANEOPS_INSTANCE, ~/.config/planeops, or cwd",
    )
    sub = parser.add_subparsers(dest="verb", required=True)
    for verb in _VERBS:
        verb.register(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    from planeops.core.schema import SchemaError

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return cast(int, args.func(args))
    except (SchemaError, FileNotFoundError, LookupError, NotImplementedError) as exc:
        # One choke point for the expected operator errors (bad registry YAML,
        # missing/torn snapshot, unknown --id, unsupported platform): every
        # verb, current and future, gets the same clean message + exit 1
        # instead of each handler re-implementing the catch.
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
