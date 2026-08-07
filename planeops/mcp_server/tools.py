"""What the MCP tools actually do: thin pass-throughs to the engine's read verbs.

No `mcp` import here on purpose, so this stays testable without the optional
dependency and can never drift from the planeops. `drift_state` returns exactly the
structure the CLI's `plane drift --json` emits (`drift_report_dict`); `observe_state`
summarizes the snapshot run_observe already writes. Neither re-implements triage.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from planeops.adapters.mcp.view import read_mcp_view
from planeops.core.contracts import Adapter, Platform
from planeops.core.drift import run_drift
from planeops.core.observe import run_observe
from planeops.core.report import drift_report_dict
from planeops.core.schema import SchemaError
from planeops.core.status import read_status


def observe_state(
    repo_root: Path,
    *,
    now: datetime | None = None,
    platform: Platform | None = None,
    adapters: dict[str, Adapter] | None = None,
) -> dict[str, Any]:
    """Scan the machine (read-only) and return a compact inventory summary: how many
    items each adapter observed, plus declared-but-uncovered adapters and any that
    failed. The full snapshot is written to disk as usual."""
    snap = run_observe(repo_root, now=now, platform=platform, adapters=adapters)
    by_adapter: dict[str, int] = {}
    for obs in snap["observed"]:
        by_adapter[obs["adapter"]] = by_adapter.get(obs["adapter"], 0) + 1
    return {
        "host": snap["host"],
        "ts": snap["ts"],
        "observed_count": len(snap["observed"]),
        "by_adapter": dict(sorted(by_adapter.items())),
        "uncovered": snap["uncovered"],
        "failed": snap["failed"],
    }


def drift_state(
    repo_root: Path,
    *,
    now: datetime | None = None,
    platform: Platform | None = None,
    implemented: set[str] | None = None,
) -> dict[str, Any]:
    """Diff the last snapshot against desired state and return the result as
    structured data (identical to `plane drift --json`). A pure read: it writes no
    files (`write=False`), so an assistant can call it freely without churning the
    repo. The two expected operator conditions, no snapshot yet (observe first) and
    an invalid registry, come back as a structured `{"error": ...}` rather than
    raising across the tool boundary. For a fresh answer, call observe_state first,
    then this."""
    try:
        report = run_drift(
            repo_root, now=now, platform=platform, implemented=implemented, write=False
        )
    except (FileNotFoundError, SchemaError) as exc:
        return {"error": str(exc)}
    return drift_report_dict(report)


def status_state(
    repo_root: Path, *, platform: Platform | None = None
) -> dict[str, Any]:
    """The last drift report from `DRIFT.json`, no rescan (identical to `plane
    status --json`). The cheap "is there drift right now?" read. `{"error": ...}` when
    no report has been written yet; never scans the machine or writes."""
    data = read_status(repo_root, platform=platform)
    return data if data is not None else {"error": "no drift report yet; run drift"}


def secrets_names(repo_root: Path) -> dict[str, Any]:
    """The secret NAMES in the configured store, never a value (identical to
    `plane secrets list`). A pure read against the store file: no scan, no
    decrypt, no write. `{"error": ...}` when no store is configured or the
    store kind cannot enumerate."""
    from planeops.secrets import EnumeratesKeys
    from planeops.secrets.resolve import resolve_store

    store = resolve_store(repo_root)
    if store is None:
        return {"error": "no secrets store is configured or shipped as default"}
    if not isinstance(store, EnumeratesKeys):
        return {"error": f"the {store.name!r} store cannot list its keys"}
    try:
        names = sorted(store.keys())
    except ValueError as exc:  # a plaintext store is refused, not listed
        return {"error": str(exc)}
    return {"names": names, "count": len(names)}


def mcp_view_state(
    repo_root: Path, *, platform: Platform | None = None
) -> dict[str, Any]:
    """The cross-client MCP view from the last snapshot (identical to `plane mcp
    --json`): every MCP server and which clients it is wired into, flagging single-
    client, name-drift, and ungoverned servers. `{"error": ...}` when no snapshot
    exists yet; a pure read, never scans or writes."""
    view = read_mcp_view(repo_root, platform=platform)
    return view if view is not None else {"error": "no snapshot yet; run observe"}
