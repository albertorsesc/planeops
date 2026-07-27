"""`plane drift`: diff desired (registry) against observed (snapshot).

Triage follows SPEC.md section 5. Exit code 2 (surfaced by the CLI) when any
alert exists.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from engine.core.contracts import Observed, Platform
from engine.core.discovery import discover_adapters
from engine.core.observe import snapshot_path
from engine.core.registry import load_registry
from engine.core.schema import ABSENT_LIFECYCLES, Auth, Entry, Lifecycle, Tolerance


@dataclass(frozen=True, slots=True)
class DriftItem:
    entry_id: str
    lifecycle: str
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
        message=message,
    )


def _same_major(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a.split(".", 1)[0] == b.split(".", 1)[0]


def _soft_section(report: DriftReport, tolerance: Tolerance) -> list[DriftItem]:
    """Where a soft (non-structural) drift signal lands, per the entry's tolerance:
    `alert` escalates it, `auto` folds it silently, `report` (default) lists it.
    Structural lifecycle/presence violations are not routed here; they stay alerts
    regardless, so `tolerance: auto` can never silence a broken active service."""
    if tolerance is Tolerance.alert:
        return report.alerts
    if tolerance is Tolerance.auto:
        return report.auto_folded
    return report.report


def triage(
    entries: Iterable[Entry],
    observed_by_key: dict[str, Observed],
    implemented: set[str],
) -> DriftReport:
    report = DriftReport(host="", ts="")
    for entry in entries:
        # The re-auth checklist is coverage-independent: any interactive
        # credential contributes a line even when its adapter is unbuilt.
        if entry.auth is Auth.interactive:
            report.reauth.append(
                _item(entry, "interactive credential; re-auth after migration")
            )

        if entry.adapter not in implemented:
            report.uncovered.append(
                _item(entry, f"awaiting the {entry.adapter!r} adapter")
            )
            continue

        obs = observed_by_key.get(entry.id)

        if entry.lifecycle in ABSENT_LIFECYCLES:
            if obs is not None:
                report.alerts.append(
                    _item(
                        entry,
                        f"listed {entry.lifecycle.value} but still observed present",
                    )
                )
        elif obs is None:
            if entry.lifecycle in (Lifecycle.active, Lifecycle.maintain):
                report.alerts.append(_item(entry, "expected present, not observed"))
            else:
                report.report.append(_item(entry, "parked but not observed"))
        else:
            if obs.facts.get("stale"):
                _soft_section(report, entry.tolerance).append(
                    _item(
                        entry,
                        "attestation stale (>30d); run `plane observe --attest`",
                    )
                )
            if obs.facts.get("drifted"):
                _soft_section(report, entry.tolerance).append(
                    _item(entry, "drifted from its declared source; apply to converge")
                )
            if (
                entry.pin
                and _same_major(obs.version, entry.pin)
                and obs.version != entry.pin
            ):
                _soft_section(report, entry.tolerance).append(
                    _item(
                        entry,
                        f"version {obs.version} (pinned {entry.pin}, same major)",
                    )
                )

    return report


def run_drift(
    repo_root: Path,
    *,
    now: datetime | None = None,
    platform: Platform | None = None,
    implemented: set[str] | None = None,
) -> DriftReport:
    from engine.core.report import render_drift  # local import avoids cycle
    from engine.platform import current_platform

    now = now or datetime.now()
    platform = platform or current_platform()
    implemented = set(discover_adapters()) if implemented is None else implemented

    registry_dir = repo_root / "registry"
    observed_dir = repo_root / "observed"

    snap_path = snapshot_path(observed_dir, platform.hostname())
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

    result = triage(entries, observed_by_key, implemented)
    result.host = host
    result.ts = now.isoformat()

    drift_md = observed_dir / host / "DRIFT.md"
    drift_md.parent.mkdir(parents=True, exist_ok=True)
    drift_md.write_text(render_drift(result))
    return result
