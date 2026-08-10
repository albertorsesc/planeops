"""`plane drift`: diff desired (registry) against observed (snapshot).

Triage follows SPEC.md section 5. Exit code 2 (surfaced by the CLI) when any
alert exists.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from planeops.core.contracts import Observed, Platform
from planeops.core.discovery import discover_adapters
from planeops.core.observe import load_observed, load_snapshot
from planeops.core.registry import load_registry
from planeops.core.report import (
    DriftItem,
    DriftReport,
    render_drift,
    render_drift_json,
)
from planeops.core.schema import ABSENT_LIFECYCLES, Auth, Entry, Lifecycle, Tolerance
from planeops.core.statefile import atomic_write


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
        # credential contributes a line even when its adapter is unbuilt. A
        # credential whose observation says configured has been restored and
        # drops off; the checklist must empty as the human works it, never
        # stand as a permanent fixture.
        if entry.auth is Auth.interactive and entry.lifecycle in (
            Lifecycle.active,
            Lifecycle.maintain,
        ):
            obs = observed_by_key.get(entry.id)
            if not (obs and obs.facts.get("configured")):
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
            # An adapter may declare what "present" means for its domain via a
            # `present` fact (a service: loaded/enabled, not file-on-disk), so a
            # retired, booted-out service whose file remains is conformant
            # instead of a forever-alert apply can never plan away. No fact means
            # observed-at-all IS presence (package adapters).
            if obs is not None and bool(obs.facts.get("present", True)):
                report.alerts.append(
                    _item(
                        entry,
                        f"listed {entry.lifecycle.value} but still observed present",
                    )
                )
            else:
                # Reality converged: the entry was a work order and the work is
                # done. The registry holds current intent, not history (git
                # does), so the closing move is deleting the line.
                report.report.append(
                    _item(
                        entry,
                        f"{entry.lifecycle.value} complete; "
                        "remove the entry from the registry",
                    )
                )
        elif obs is None:
            if entry.lifecycle in (Lifecycle.active, Lifecycle.maintain):
                report.alerts.append(_item(entry, "expected present, not observed"))
            else:
                report.report.append(_item(entry, "parked but not observed"))
        else:
            unconfigured = obs.facts.get("configured") is False and entry.lifecycle in (
                Lifecycle.active,
                Lifecycle.maintain,
            )
            if unconfigured:
                # A parked secret is deliberately dormant: unconfigured is its
                # expected state, not a violation.
                report.alerts.append(_item(entry, "required secret is not configured"))
            elif not bool(obs.facts.get("present", True)) and entry.lifecycle in (
                Lifecycle.active,
                Lifecycle.maintain,
            ):
                # The adapter looked and found nothing present (a service booted
                # out, an asset gone), which is the same violation as observing
                # nothing at all. Structural, so tolerance can never fold it,
                # and second to the unconfigured branch because that message
                # names the domain's own remedy. The soft signals below describe
                # a thing that is not there, so they are skipped exactly as the
                # nothing-observed branch skips them.
                report.alerts.append(_item(entry, "expected present, not observed"))
                continue
            if obs.facts.get("stale"):
                _soft_section(report, entry.tolerance).append(
                    _item(
                        entry,
                        "attestation stale (>30d); run `plane observe --attest`",
                    )
                )
            if obs.facts.get("drifted") and entry.lifecycle in (
                Lifecycle.active,
                Lifecycle.maintain,
            ):
                # A parked asset deviating from its own definition (a
                # start-at-login service sitting unloaded) IS dormancy, and
                # apply plans nothing for parked; a report would nag forever.
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
            # Checked before attribution on purpose: something that runs code
            # on its own must alert even when a name-matched entry claims it,
            # because attribution is evidence of a decision, not a license.
            report.alerts.append(
                DriftItem(
                    key,
                    "unregistered",
                    "ungoverned always-on service; declare it or add an unmanaged glob",
                )
            )
        elif (
            isinstance(governed_by := obs.facts.get("governed_by"), str)
            and governed_by in declared_ids
        ):
            # Evidence attributed to an entry that already governs the tool:
            # the decision exists, nothing to ask. A stale attribution falls
            # through and stays visible.
            pass
        else:
            report.ungoverned.append(
                DriftItem(key, "unregistered", "observed but not in the registry")
            )

    # A failed scan alerts through its entries ("state unknown" lines), but
    # only when the adapter has entries AND counts as implemented; in every
    # other combination the failure would vanish, and a configured adapter
    # that could not scan is a coverage hole, so the adapter itself alerts.
    covered_by_entries = {e.adapter for e in entries} & implemented
    for adapter_name in sorted(failed):
        if adapter_name not in covered_by_entries:
            report.alerts.append(
                DriftItem(
                    adapter_name,
                    "scan-failed",
                    f"adapter scan failed ({failed[adapter_name]}); "
                    "coverage lost until fixed",
                )
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
    from planeops.platform import current_platform

    now = now or datetime.now()
    platform = platform or current_platform()
    implemented = set(discover_adapters()) if implemented is None else implemented

    registry_dir = repo_root / "registry"
    observed_dir = repo_root / "observed"

    snapshot = load_snapshot(observed_dir, platform.hostname())
    host = snapshot.get("host") or platform.hostname()
    observed_by_key = load_observed(snapshot)

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
