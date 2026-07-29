"""`plane mcp`: a cross-client view of MCP servers from the last snapshot.

A pure read of `observed/<host>/snapshot.json` (what `plane observe` already wrote),
turned into the one thing no single tool's config shows: every MCP server and which
clients each is wired into. Same read-only, no-recompute posture as `plane status`.

Three call-outs the merged picture makes visible and no per-client config does:
- servers wired into only one client (candidates to reuse in the others),
- the same tool under different names across clients (naming drift), and
- servers observed on the machine but absent from the registry (ungoverned).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.core.contracts import Platform


def _normalize(name: str) -> str:
    """Collapse a server name to a comparison key so `mcp-foo` and `foo` (one tool
    wired under different names in different clients) land together. Case- and
    separator-insensitive; strips a leading `mcp` token and a trailing `mcp`/`server`
    token, the common wrapping noise. Deliberately conservative: it strips no
    meaningful words, so distinct tools stay distinct."""
    s = "".join(c for c in name.lower() if c.isalnum())
    if s.startswith("mcp"):
        s = s[3:]
    for suffix in ("server", "mcp"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return s


def build_mcp_view(snapshot: dict[str, Any], declared_ids: set[str]) -> dict[str, Any]:
    """Turn a snapshot (plus the set of declared entry ids) into the MCP view. Pure:
    no IO, no machine access. Reads only `adapter == "mcp"` observations; other
    adapters' facts are ignored."""
    servers: list[dict[str, Any]] = []
    for obs in snapshot.get("observed", []):
        if not isinstance(obs, dict) or obs.get("adapter") != "mcp":
            continue
        name = obs.get("native_id")
        if not isinstance(name, str):
            continue
        facts = obs.get("facts")
        raw = facts.get("sources") if isinstance(facts, dict) else None
        raw = raw if isinstance(raw, list) else []
        clients = sorted(c for c in raw if isinstance(c, str))
        server_id = f"mcp/{name}"
        servers.append(
            {
                "name": name,
                "id": server_id,
                "clients": clients,
                "governed": server_id in declared_ids,
            }
        )
    servers.sort(key=lambda s: s["name"])

    groups: dict[str, list[str]] = {}
    for s in servers:
        groups.setdefault(_normalize(s["name"]), []).append(s["name"])

    return {
        "host": snapshot.get("host"),
        "ts": snapshot.get("ts"),
        "servers": servers,
        "single_client": [s["name"] for s in servers if len(s["clients"]) == 1],
        "ungoverned": [s["name"] for s in servers if not s["governed"]],
        "name_drift": [
            {"names": sorted(names)}
            for _, names in sorted(groups.items())
            if len(set(names)) > 1
        ],
    }


def read_mcp_view(
    repo_root: Path, *, platform: Platform | None = None
) -> dict[str, Any] | None:
    """The MCP view for this host from the last snapshot, or None if none exists.
    Reads `observed/<host>/snapshot.json` and the registry (to mark governed vs
    ungoverned); never scans the machine or writes. Torn-read safe, like
    `read_status`: a half-written snapshot reads as "no view", never a traceback."""
    from engine.core.registry import load_registry
    from engine.platform import current_platform

    platform = platform or current_platform()
    path = repo_root / "observed" / platform.hostname() / "snapshot.json"
    if not path.is_file():
        return None
    try:
        snapshot: dict[str, Any] = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    declared_ids = {e.id for e in load_registry(repo_root / "registry").entries}
    return build_mcp_view(snapshot, declared_ids)


def render_mcp_view(view: dict[str, Any]) -> str:
    """Human-readable rendering: a `server -> clients` table, then the single-client,
    ungoverned, and name-drift call-outs."""
    servers = view["servers"]
    host = view.get("host") or "this host"
    ts = view.get("ts")
    lines = [f"MCP servers on {host}" + (f" (as of {ts})" if ts else "") + ":", ""]
    if not servers:
        lines.append(
            "  (none observed; add mcp.sources to instance.yaml, then `plane observe`)"
        )
        return "\n".join(lines) + "\n"

    width = max(len(s["name"]) for s in servers)
    for s in servers:
        clients = ", ".join(s["clients"]) or "(none)"
        tag = "" if s["governed"] else "  (ungoverned)"
        lines.append(f"  {s['name']:<{width}}  {clients}{tag}")

    if view["single_client"]:
        joined = ", ".join(view["single_client"])
        lines += ["", f"single-client (reuse candidates): {joined}"]
    if view["ungoverned"]:
        joined = ", ".join(view["ungoverned"])
        lines.append(f"ungoverned (observed, not in the registry): {joined}")
    if view["name_drift"]:
        lines.append("name drift (same tool, different names):")
        lines += ["  " + ", ".join(g["names"]) for g in view["name_drift"]]
    return "\n".join(lines) + "\n"
