"""`plane import`: propose registry entries from a manifest (module named
import_ because `import` is a keyword; the verb is still `plane import`)."""

from __future__ import annotations

import argparse
from pathlib import Path

from planeops.cli._text import n_entries
from planeops.cli.instance import instance_root


def _cmd(args: argparse.Namespace) -> int:
    from planeops.importers import discover_importers, render_proposal, write_proposal
    from planeops.providers import ui

    repo = instance_root(args)
    if args.path is not None:
        path = Path(args.path)
    elif args.kind == "observed":
        # The CLI computes this path everywhere else; retyping it was pure
        # friction. `plane import observed` alone reads the host's own snapshot.
        from planeops.core.observe import snapshot_path
        from planeops.platform import current_platform

        path = snapshot_path(repo / "observed", current_platform().hostname())
    else:
        ui.err(f"import {args.kind} requires a path")
        return 1
    if not path.is_file():
        ui.err(f"no such file: {path}")
        return 1

    importer = discover_importers().get(args.kind)
    if importer is None:  # argparse choices normally prevents this
        ui.err(f"unknown import kind {args.kind!r}")
        return 1
    entries = importer.propose(path.read_text(), repo)
    if args.adapter:  # onboard one type at a time (e.g. --adapter mcp)
        entries = [e for e in entries if e.get("adapter") == args.adapter]
        if not entries:  # clarify 0 results vs an unrecognized adapter name
            ui.note(f"note: --adapter {args.adapter!r} matched no proposed entries")
    ui.line(importer.note(path, len(entries)))

    if not args.write:  # default: propose to stdout, write nothing
        print(render_proposal(entries), end="")  # pipeable YAML, no styling
        return 0

    # --write: land the proposal into registry/imported.yaml (a prune-not-author seed).
    if not entries:
        ui.line("nothing new to import; the registry already covers the observed items")
        return 0
    target = repo / "registry" / "imported.yaml"
    if not args.yes:  # show the proposal and confirm before mutating the registry
        print(render_proposal(entries), end="")  # pipeable YAML, no styling
        try:
            answer = input(f"write {n_entries(len(entries))} to {target}? (y/N) ")
        except (EOFError, OSError):
            answer = ""  # no readable stdin: never write without an explicit --yes
        if answer.strip().lower()[:1] != "y":
            ui.note("not written (use --yes to write non-interactively)")
            return 0
    written, total = write_proposal(entries, repo)
    ui.good(f"added {n_entries(len(entries))} to {written} ({total} total)")
    ui.line("prune registry/imported.yaml to taste, then `plane drift`")
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    from planeops.importers import discover_importers

    p = sub.add_parser(
        "import",
        help="propose registry entries from a manifest",
        description=(
            "Turn a manifest into proposed registry entries: 'observed' reads "
            "this host's own snapshot and proposes everything the registry does "
            "not govern yet; other kinds read a file you point at. Default is "
            "propose-only to stdout; --write lands the proposal into "
            "registry/imported.yaml (confirmed first) for you to prune."
        ),
    )
    p.add_argument(
        "kind",
        choices=sorted(discover_importers()),
        help="what to import from (discovered importers)",
    )
    p.add_argument(
        "path",
        nargs="?",
        default=None,
        help="manifest to read (default for 'observed': the host's own snapshot)",
    )
    p.add_argument(
        "--adapter",
        default=None,
        help="propose only entries for this adapter (onboard one type at a time)",
    )
    p.add_argument(
        "--write",
        action="store_true",
        help="land the proposal into registry/imported.yaml (de-duped) to prune",
    )
    p.add_argument(
        "--yes", action="store_true", help="with --write, skip the confirmation prompt"
    )
    p.set_defaults(func=_cmd)
