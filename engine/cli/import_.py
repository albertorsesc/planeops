"""`plane import`: propose registry entries from a manifest (module named
import_ because `import` is a keyword; the verb is still `plane import`)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engine.cli.instance import instance_root


def _cmd(args: argparse.Namespace) -> int:
    from engine.importers import discover_importers, render_proposal, write_proposal

    repo = instance_root(args)
    if args.path is not None:
        path = Path(args.path)
    elif args.kind == "observed":
        # The CLI computes this path everywhere else; retyping it was pure
        # friction. `plane import observed` alone reads the host's own snapshot.
        from engine.core.observe import snapshot_path
        from engine.platform import current_platform

        path = snapshot_path(repo / "observed", current_platform().hostname())
    else:
        print(f"import {args.kind} requires a path", file=sys.stderr)
        return 1
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 1

    importer = discover_importers().get(args.kind)
    if importer is None:  # argparse choices normally prevents this
        print(f"unknown import kind {args.kind!r}", file=sys.stderr)
        return 1
    entries = importer.propose(path.read_text(), repo)
    if args.adapter:  # onboard one type at a time (e.g. --adapter mcp)
        entries = [e for e in entries if e.get("adapter") == args.adapter]
        if not entries:  # clarify 0 results vs an unrecognized adapter name
            print(
                f"note: --adapter {args.adapter!r} matched no proposed entries",
                file=sys.stderr,
            )
    print(importer.note(path, len(entries)))

    if not args.write:  # default: propose to stdout, write nothing
        print(render_proposal(entries), end="")
        return 0

    # --write: land the proposal into registry/imported.yaml (a prune-not-author seed).
    if not entries:
        print("nothing new to import; the registry already covers the observed items")
        return 0
    target = repo / "registry" / "imported.yaml"
    if not args.yes:  # show the proposal and confirm before mutating the registry
        print(render_proposal(entries), end="")
        try:
            answer = input(f"write {len(entries)} entries to {target}? (y/N) ")
        except (EOFError, OSError):
            answer = ""  # no readable stdin: never write without an explicit --yes
        if answer.strip().lower()[:1] != "y":
            print("not written (use --yes to write non-interactively)", file=sys.stderr)
            return 0
    written, total = write_proposal(entries, repo)
    print(f"wrote {len(entries)} new entries to {written} ({total} total)")
    print("prune registry/imported.yaml to taste, then `plane drift`")
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    from engine.importers import discover_importers

    p = sub.add_parser("import", help="propose registry entries from a manifest")
    p.add_argument("kind", choices=sorted(discover_importers()))
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
