"""`plane mcp`: cross-client view of MCP servers from the last snapshot."""

from __future__ import annotations

import argparse
import json
import sys

from engine.cli.instance import instance_root


def _cmd(args: argparse.Namespace) -> int:
    from engine.adapters.mcp.view import read_mcp_view, render_mcp_view

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
