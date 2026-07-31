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
from engine.core.statefile import atomic_write


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
    ungoverned: list[DriftItem] = field(default_factory=list)
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
    failed: dict[str, str] | None = None,
) -> DriftReport:
    failed = failed or {}
    report = DriftReport(host="", ts="")
    entries = list(entries)  # walked twice: per-entry triage, then dependency checks
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

        if entry.adapter in failed:
            # The adapter crashed during observe, so this entry's real state is
            # unknown. "expected present, not observed" would be a false story
            # (the machine may be fine); say what actually happened.
            report.alerts.append(
                _item(
                    entry,
                    f"adapter scan failed ({failed[entry.adapter]}); state unknown",
                )
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
            if obs.facts.get("configured") is False:
                report.alerts.append(_item(entry, "required secret is not configured"))
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

    # Ungoverned pass: observed on the machine, absent from the registry. The
    # snapshot is already post-unmanaged, so everything here is neither declared
    # nor deliberately excluded. An item whose own facts say it is always-on (an
    # adapter-declared general fact: a login/keepalive/interval agent, an enabled
    # unit) will run code without ever having been declared, the one thing a
    # control plane must never stay silent about, so it alerts; anything else is
    # surfaced for `plane import observed` to propose or an unmanaged glob to
    # exclude.
    declared_ids = {e.id for e in entries}
    for key in sorted(observed_by_key):
        if key in declared_ids:
            continue
        obs = observed_by_key[key]
        if obs.facts.get("always_on"):
            report.alerts.append(
                DriftItem(
                    key,
                    "unregistered",
                    "ungoverned always-on service; declare it or add an unmanaged glob",
                )
            )
        else:
            report.ungoverned.append(
                DriftItem(key, "unregistered", "observed but not in the registry")
            )

    # Dependency integrity: an active/maintain entry that `needs` something being
    # retired/purged or absent is an alert, so a resource a consumer depends on
    # (e.g. an embedding model a tool uses) can't be pruned out from under it.
    by_id = {e.id: e for e in entries}
    for entry in entries:
        if entry.lifecycle not in (Lifecycle.active, Lifecycle.maintain):
            continue
        for need in entry.needs:
            dep = by_id.get(need)
            # A dep whose adapter isn't built can't be judged present/absent (same
            # coverage gate the per-entry pass uses), so it's never a false "absent".
            judgeable = dep is None or dep.adapter in implemented
            if dep is not None and dep.lifecycle in ABSENT_LIFECYCLES:
                report.alerts.append(
                    _item(entry, f"needs {need}, which is listed {dep.lifecycle.value}")
                )
            elif judgeable and need not in observed_by_key:
                report.alerts.append(
                    _item(entry, f"needs {need}, which is not present")
                )

    return report


def run_drift(
    repo_root: Path,
    *,
    now: datetime | None = None,
    platform: Platform | None = None,
    implemented: set[str] | None = None,
    write: bool = True,
) -> DriftReport:
    from engine.core.report import (  # local import avoids cycle
        render_drift,
        render_drift_json,
    )
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

    failed = {
        f["adapter"]: str(f.get("error", ""))
        for f in snapshot.get("failed", [])
        if isinstance(f, dict) and isinstance(f.get("adapter"), str)
    }
    result = triage(entries, observed_by_key, implemented, failed=failed)
    result.host = host
    result.ts = now.isoformat()

    if write:  # a pure-read caller (e.g. the MCP drift tool) passes write=False
        out_dir = observed_dir / host
        out_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(out_dir / "DRIFT.md", render_drift(result))  # human pane
        atomic_write(out_dir / "DRIFT.json", render_drift_json(result))  # machine
    return result
