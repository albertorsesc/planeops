"""`plane drift`: diff desired (registry) against observed (snapshot).

Triage follows SPEC.md section 5. Exit code 2 (surfaced by the CLI) when any
alert exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from engine.core.contracts import Observed
from engine.core.discovery import discover_adapters
from engine.core.observe import snapshot_path
from engine.core.registry import load_registry
from engine.core.schema import ABSENT_LIFECYCLES, Auth, Entry, Lifecycle


@dataclass(frozen=True, slots=True)
class DriftItem:
    entry_id: str
    lifecycle: str
    tolerance: str
    message: str


@dataclass(slots=True)
class DriftReport:
    host: str
    ts: str
    alerts: list[DriftItem] = field(default_factory=list)
    report: list[DriftItem] = field(default_factory=list)
    auto_folded: list[DriftItem] = field(default_factory=list)
    uncovered: list[DriftItem] = field(default_factory=list)
    reauth: list[DriftItem] = field(default_factory=list)

    @property
    def alert_count(self) -> int:
        return len(self.alerts)


def _item(entry: Entry, message: str) -> DriftItem:
    return DriftItem(
        entry_id=entry.id,
        lifecycle=entry.lifecycle.value,
        tolerance=entry.tolerance.value,
        message=message,
    )


def _same_major(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a.split(".", 1)[0] == b.split(".", 1)[0]


def triage(entries, observed_by_key: dict[str, Observed], implemented: set[str]) -> DriftReport:
    report = DriftReport(host="", ts="")
    for entry in entries:
        # The re-auth checklist is coverage-independent: any interactive
        # credential contributes a line even when its adapter is unbuilt
        # (SPEC.md 05 section 1).
        if entry.auth is Auth.interactive:
            report.reauth.append(_item(entry, "interactive credential; re-auth after migration"))

        if entry.adapter not in implemented:
            report.uncovered.append(_item(entry, f"awaiting the {entry.adapter!r} adapter"))
            continue

        obs = observed_by_key.get(entry.id)
        present = obs is not None

        if entry.lifecycle in ABSENT_LIFECYCLES:
            if present:
                report.alerts.append(
                    _item(entry, f"listed {entry.lifecycle.value} but still observed present")
                )
        else:
            if not present:
                if entry.lifecycle in (Lifecycle.active, Lifecycle.maintain):
                    report.alerts.append(_item(entry, "expected present, not observed"))
                else:
                    report.report.append(_item(entry, "parked but not observed"))
            else:
                if obs.facts.get("stale"):
                    report.report.append(
                        _item(entry, "attestation stale (>30d); run `plane observe --attest`")
                    )
                if entry.pin and _same_major(obs.version, entry.pin) and obs.version != entry.pin:
                    report.auto_folded.append(
                        _item(entry, f"version {obs.version} (pinned {entry.pin}, same major)")
                    )

    return report


def run_drift(repo_root: Path, *, now: datetime | None = None) -> DriftReport:
    from engine.core.report import render_drift  # local import avoids cycle

    now = now or datetime.now()
    registry_dir = repo_root / "registry"
    observed_dir = repo_root / "observed"

    from engine.platform import current_platform

    host = current_platform().hostname()
    snap_path = snapshot_path(observed_dir, host)
    if not snap_path.is_file():
        raise FileNotFoundError(
            f"no snapshot at {snap_path}; run `plane observe` first"
        )

    snapshot = json.loads(snap_path.read_text())
    host = snapshot["host"]
    observed_by_key = {
        o.key: o for o in (Observed.from_dict(d) for d in snapshot.get("observed", []))
    }

    registry = load_registry(registry_dir)
    entries = registry.entries_for_host(host)
    implemented = set(discover_adapters())

    result = triage(entries, observed_by_key, implemented)
    result.host = host
    result.ts = now.isoformat()

    drift_md = observed_dir / host / "DRIFT.md"
    drift_md.parent.mkdir(parents=True, exist_ok=True)
    drift_md.write_text(render_drift(result))
    return result
