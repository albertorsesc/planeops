"""Import the machine's own observed snapshot into proposed registry entries.

`plane observe` already inventories the machine into observed/<host>/snapshot.json;
this scaffolds candidate entries from it, so onboarding is prune-a-list rather than
hand-author-from-blank. Proposes one entry per observed item that is neither
already declared nor exempted by an `unmanaged` glob, each as active/verify for
the human to curate: keep what matters (e.g. brew leaves), drop the rest
(transitive deps, bundled packages). Nothing is written; the CLI prints the
proposal for review. The domain comes from the observing adapter, since the
observed snapshot records the adapter but not the (registry-only) domain.

An exempted item that runs code at login is proposed anyway: drift alerts on it and
names declaring it as the remedy, so the tool that writes declarations has to offer
the one the report asks for.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from planeops.core.discovery import discover_adapters
from planeops.core.observe import exemption_holds, unmanaged_exemptions
from planeops.core.registry import load_registry


def _domain_by_adapter() -> dict[str, str]:
    """adapter name -> its primary domain, for the proposed entry's `domain`."""
    return {
        name: (adapter.domains[0] if adapter.domains else "unknown")
        for name, adapter in discover_adapters().items()
    }


def propose_from_snapshot(text: str, repo_root: Path | None) -> list[dict[str, Any]]:
    """Proposed entries for every observed item not already declared. Pure; a
    malformed or non-object snapshot yields no proposals rather than raising."""
    try:
        snap = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(snap, dict):
        return []

    observed = snap.get("observed")
    if not isinstance(observed, list):
        return []  # present-but-null or the wrong type: no proposals, never raise

    declared: set[str] = set()
    if repo_root is not None:
        # Entry ids are globally unique, so skip against ALL declared ids, not just
        # this host's: a same-id entry declared for another host would otherwise be
        # re-proposed, and the saved registry would then fail load on a duplicate id.
        declared = {e.id for e in load_registry(repo_root / "registry").entries}

    unmanaged = unmanaged_exemptions(snap)
    domains = _domain_by_adapter()
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for obs in observed:
        if not isinstance(obs, dict):
            continue
        adapter = obs.get("adapter")
        native = obs.get("native_id")
        if not isinstance(adapter, str) or not isinstance(native, str):
            continue
        entry_id = f"{adapter}/{native}"
        if entry_id in declared or entry_id in seen:
            continue
        seen.add(entry_id)
        facts = obs.get("facts")
        always_on = bool(isinstance(facts, dict) and facts.get("always_on"))
        if exemption_holds(unmanaged.get(entry_id), always_on=always_on):
            continue
        governed_by = facts.get("governed_by") if isinstance(facts, dict) else None
        if isinstance(governed_by, str) and governed_by in declared:
            # Attributed to a decision already on record. This check spans
            # every host's entries (drift's is host-scoped) because a same-id
            # entry anywhere already forbids proposing the id again.
            continue
        # Seeding must DESCRIBE the machine, never propose changes to it: an
        # asset that is on disk but not active (facts.present False, e.g. an
        # unloaded agent) seeds as `parked`, so a fresh registry plans nothing.
        inactive = isinstance(facts, dict) and facts.get("present") is False
        entry: dict[str, Any] = {
            "id": entry_id,
            "adapter": adapter,
            "domain": domains.get(adapter, "unknown"),
            "lifecycle": "parked" if inactive else "active",
            "tolerance": "report",
            "intent": (
                "imported from observed snapshot (on disk, not active); verify"
                if inactive
                else "imported from observed snapshot, verify"
            ),
        }
        logs = facts.get("logs") if isinstance(facts, dict) else None
        if isinstance(logs, list) and logs:
            entry["logs"] = [str(x) for x in logs]
        entries.append(entry)
    # Grouped by adapter (type) so the proposal reads by type, not as one flat wall.
    entries.sort(key=lambda e: (e["adapter"], e["id"]))
    return entries


class ObservedImporter:
    kind = "observed"

    def propose(self, text: str, repo_root: Path | None) -> list[dict[str, Any]]:
        return propose_from_snapshot(text, repo_root)

    def note(self, path: Path, count: int) -> str:
        return (
            f"# proposed {count} entr(ies) from the observed snapshot {path} "
            "- prune (drop deps/bundled), then save into registry/"
        )


IMPORTER = ObservedImporter()

__all__ = ["IMPORTER", "ObservedImporter", "propose_from_snapshot"]
