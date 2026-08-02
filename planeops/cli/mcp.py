"""`plane mcp`: cross-client view of MCP servers from the last snapshot."""

from __future__ import annotations

import argparse
import json
import sys

from planeops.cli.instance import instance_root


def _render_source(source: dict[str, object]) -> str:
    lines = [f"    - label: {source['label']}"]
    for field_name in ("path", "format", "key", "logs"):
        if field_name in source:
            lines.append(f"      {field_name}: {source[field_name]}")
    return "\n".join(lines)


def _cmd_init(args: argparse.Namespace) -> int:
    """Detect known clients on this machine and wire them as mcp sources,
    appending to instance.yaml without touching anything already there."""
    from pathlib import Path

    from planeops.adapters.mcp import load_sources
    from planeops.adapters.mcp.detect import detect_sources
    from planeops.core.statefile import atomic_write

    repo = instance_root(args)
    wired = {s.label for s in load_sources(repo)}
    found = [f for f in detect_sources(Path.home()) if f["label"] not in wired]
    if not found:
        print("nothing to add: every detected client is already a source")
        return 0
    print("mcp init will add these sources to instance.yaml:")
    for f in found:
        print(_render_source(f))
    if not args.yes:
        try:
            answer = input("proceed? (y/N) ")
        except (EOFError, OSError):
            answer = ""
        if answer.strip().lower()[:1] != "y":
            print("not written (use --yes to run non-interactively)", file=sys.stderr)
            return 0
    from planeops.providers import yaml

    path = repo / "instance.yaml"
    # Round-trip edit: the user's comments, order, and formatting survive; the
    # library owns nesting, so sections after mcp: are structurally safe.
    text = path.read_text() if path.is_file() else ""
    doc = yaml.edit_load(text)
    if doc is None:
        # No data yet (empty or comments-only): keep the text as a header.
        header = text.rstrip("\n") + "\n\n" if text.strip() else ""
        doc = {"mcp": {"sources": found}}
        atomic_write(path, header + yaml.edit_dump(doc))
    else:
        doc.setdefault("mcp", {}).setdefault("sources", []).extend(found)
        atomic_write(path, yaml.edit_dump(doc))
    print(f"wired {len(found)} source(s); run `plane observe` to scan them")
    return 0


def _cmd(args: argparse.Namespace) -> int:
    from planeops.adapters.mcp.view import read_mcp_view, render_mcp_view

    repo = instance_root(args)
    view = read_mcp_view(repo)  # last snapshot + registry, no recompute
    if view is None:
        if args.as_json:  # --json: stdout always parses as JSON
            print(json.dumps({"error": "no snapshot yet; run `plane observe`"}))
        else:
            print("no snapshot yet; run `plane observe`", file=sys.stderr)
        return 0
    if args.as_json:
        print(json.dumps(view, indent=2))
    else:
        print(render_mcp_view(view), end="")
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "mcp",
        help="cross-client view of MCP servers from the last snapshot (read-only)",
    )
    p.add_argument(
        "--json", dest="as_json", action="store_true",
        help="emit the MCP view as JSON",
    )  # fmt: skip
    p.set_defaults(func=_cmd)
    actions = p.add_subparsers(dest="action")
    init = actions.add_parser(
        "init", help="detect known clients and wire them as mcp sources"
    )
    init.add_argument(
        "--yes", action="store_true", help="write without the interactive confirm"
    )
    init.set_defaults(func=_cmd_init)
