"""`plane mcp`: cross-client view of MCP servers from the last snapshot."""

from __future__ import annotations

import argparse
import json

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
    from planeops.providers import ui

    repo = instance_root(args)
    wired = {s.label for s in load_sources(repo)}
    found = [f for f in detect_sources(Path.home()) if f["label"] not in wired]
    if not found:
        ui.line("nothing to add: every detected client is already a source")
        return 0
    ui.title("mcp init will add these sources to instance.yaml:")
    for f in found:
        ui.line(_render_source(f))
    if not args.yes:
        try:
            answer = input("proceed? (y/N) ")
        except (EOFError, OSError):
            answer = ""
        if answer.strip().lower()[:1] != "y":
            ui.note("not written (use --yes to run non-interactively)")
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
    ui.good(f"wired {len(found)} source(s); run `plane observe` to scan them")
    return 0


def _cmd(args: argparse.Namespace) -> int:
    from planeops.adapters.mcp.view import read_mcp_view
    from planeops.providers import ui

    repo = instance_root(args)
    view = read_mcp_view(repo)  # last snapshot + registry, no recompute
    if view is None:
        if args.as_json:  # --json: stdout always parses as JSON
            print(json.dumps({"error": "no snapshot yet; run `plane observe`"}))
        else:
            ui.note("no snapshot yet; run `plane observe`")
        return 0
    if args.as_json:
        print(json.dumps(view, indent=2))
        return 0

    from planeops.cli._text import human_ts

    host = view.get("host") or "this host"
    ts = view.get("ts")
    ui.title(f"MCP servers on {host}", detail=f"as of {human_ts(ts)}" if ts else None)
    if not view["servers"]:
        ui.line(
            "(none observed; add mcp.sources to instance.yaml, then `plane observe`)"
        )
        return 0
    flagged = any(not s["governed"] for s in view["servers"])
    headers = ["server", "clients"] + (["status"] if flagged else [])
    rows = []
    for s in view["servers"]:
        row = [s["name"], "\n".join(s["clients"]) or "(none)"]
        if flagged:
            row.append("" if s["governed"] else "~ ungoverned")
        rows.append(row)
    ui.table(headers, rows, styles=[None, None, "warn"] if flagged else None)
    if view["single_client"]:
        ui.line("single-client (reuse candidates): " + ", ".join(view["single_client"]))
    if view["ungoverned"]:
        ui.warn(
            "ungoverned (observed, not in the registry): "
            + ", ".join(view["ungoverned"])
        )
    if view["name_drift"]:
        ui.warn("name drift (same tool, different names):")
        for g in view["name_drift"]:
            ui.warn("  " + ", ".join(g["names"]))
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "mcp",
        help="cross-client view of MCP servers from the last snapshot (read-only)",
        description=(
            "Every MCP server on this machine and which clients each is wired "
            "into, merged from all configured sources in the last snapshot: the "
            "one table no single tool's config shows. Flags single-client "
            "servers (reuse candidates), the same tool under different names, "
            "and servers nobody declared."
        ),
    )
    p.add_argument(
        "--json", dest="as_json", action="store_true",
        help="emit the MCP view as JSON",
    )  # fmt: skip
    p.set_defaults(func=_cmd)
    actions = p.add_subparsers(dest="action")
    init = actions.add_parser(
        "init",
        help="detect known clients and wire them as mcp sources",
        description=(
            "Detect the known MCP clients actually installed on this machine "
            "(config present AND the client itself installed) and append them as "
            "mcp.sources in instance.yaml, previewed and confirmed; your "
            "comments and formatting survive the edit."
        ),
    )
    init.add_argument(
        "--yes", action="store_true", help="write without the interactive confirm"
    )
    init.set_defaults(func=_cmd_init)
