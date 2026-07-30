"""What the MCP tools actually do: thin pass-throughs to the engine's read verbs.

No `mcp` import here on purpose, so this stays testable without the optional
dependency and can never drift from the engine. `drift_state` returns exactly the
structure the CLI's `plane drift --json` emits (`drift_report_dict`); `observe_state`
summarizes the snapshot run_observe already writes. Neither re-implements triage.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from engine.core.contracts import Adapter, Platform
from engine.core.drift import run_drift
from engine.core.observe import run_observe
from engine.core.report import drift_report_dict
from engine.core.schema import SchemaError


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
