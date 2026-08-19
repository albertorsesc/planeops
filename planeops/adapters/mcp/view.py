"""`plane mcp`: a cross-client view of MCP servers from the last snapshot.

Lives beside the adapter that owns the facts it reads: the view interprets this
adapter's `facts["sources"]` schema, so it belongs here, not in core (which
stays adapter-generic and, per the fitness tests, never names one).

A pure read of `observed/<host>/snapshot.json` (what `plane observe` already wrote),
turned into the one thing no single tool's config shows: every MCP server and which
clients each is wired into. Same read-only, no-recompute posture as `plane status`.

Three call-outs the merged picture makes visible and no per-client config does:
- servers wired into only one client (candidates to reuse in the others),
- the same tool under different names across clients (naming drift), and
- servers observed on the machine but absent from the registry (ungoverned).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from planeops.core.contracts import Platform
from planeops.core.observe import unmanaged_exemptions
from planeops.core.statefile import read_host_json


def _normalize(name: str) -> str:
    """Collapse a server name to a comparison key so `mcp-foo` and `foo` (one tool
    wired under different names in different clients) land together. Case- and
    separator-insensitive; strips a leading `mcp` token and a trailing `mcp`/`server`
    token, the common wrapping noise. Deliberately conservative: it strips no
    meaningful words, so distinct tools stay distinct."""
    s = "".join(c for c in name.lower() if c.isalnum())
    stripped = s
    if stripped.startswith("mcp"):
        stripped = stripped[3:]
    for suffix in ("server", "mcp"):
        if stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)]
    # If stripping consumed the whole name (e.g. "mcp", "mcp-server"), fall back to
    # the unstripped key so unrelated wrapper-only names don't all collapse to "".
    return stripped or s


def build_mcp_view(snapshot: dict[str, Any], declared_ids: set[str]) -> dict[str, Any]:
    """Turn a snapshot (plus the set of declared entry ids) into the MCP view. Pure:
    no IO, no machine access. Reads only `adapter == "mcp"` observations; other
    adapters' facts are ignored.

    A server an `unmanaged` glob exempts is listed with the rest and left out of
    `ungoverned`, so the exemption means the same thing here as it does in the
    drift report."""
    unmanaged = unmanaged_exemptions(snapshot)
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
        "ungoverned": [
            s["name"] for s in servers if not s["governed"] and s["id"] not in unmanaged
        ],
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
    `read_status`: an absent, half-written, or non-object snapshot reads as "no
    view", never a traceback."""
    from planeops.core.registry import load_registry

    snapshot = read_host_json(repo_root, "snapshot.json", platform=platform)
    if snapshot is None:
        return None
    declared_ids = {e.id for e in load_registry(repo_root / "registry").entries}
    return build_mcp_view(snapshot, declared_ids)
