"""`plane observe`: run every adapter's read-only observe, write a snapshot.

Read-only and safe for the scheduled slot. Never mutates the machine.
"""

from __future__ import annotations

import fnmatch
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from planeops import __version__
from planeops.core.contracts import Adapter, Ctx, Observed, Platform
from planeops.core.discovery import discover_adapters
from planeops.core.facts import check_facts
from planeops.core.registry import Registry, load_registry
from planeops.core.statefile import atomic_write, read_json_file
from planeops.platform import current_platform
from planeops.secrets.resolve import build_handle

SNAPSHOT_SCHEMA_VERSION = 2  # bump when the snapshot / entry wire format changes


class SnapshotError(FileNotFoundError):
    """The snapshot is missing, torn, or not an object. Subclasses
    FileNotFoundError because the remedy is identical (run `plane observe`),
    so every existing handler catches it."""


def snapshot_path(observed_dir: Path, host: str) -> Path:
    return observed_dir / host / "snapshot.json"


def load_snapshot(observed_dir: Path, host: str) -> dict[str, Any]:
    """The last snapshot for `host`, parsed torn-safely. Missing, corrupt, or
    non-object files raise the same clean, actionable error instead of a
    traceback deep in json."""
    path = snapshot_path(observed_dir, host)
    snapshot = read_json_file(path)
    if snapshot is None:
        raise SnapshotError(
            f"no readable snapshot at {path}; run `plane observe` first"
        )
    return snapshot


def load_observed(snapshot: dict[str, Any]) -> dict[str, Observed]:
    """`observed` items keyed for triage. Items that are not mappings or lack
    the identifying keys (a hand-edit, an older schema) are skipped, so junk
    rows never poison a whole run."""
    out: dict[str, Observed] = {}
    for item in snapshot.get("observed", []) or []:
        if not isinstance(item, dict):
            continue
        if not isinstance(item.get("adapter"), str) or not isinstance(
            item.get("native_id"), str
        ):
            continue
        obs = Observed.from_dict(item)
        out[obs.key] = obs
    return out


def _load_prior(path: Path) -> dict[str, Observed]:
    # Torn-read safe: a snapshot killed mid-write (or otherwise corrupt) reads as
    # "no prior", so the next observe re-establishes it instead of crashing.
    raw = read_json_file(path)
    if raw is None:
        return {}
    return load_observed(raw)


def _unmanaged_matches(
    observed: list[Observed], registry: Registry, declared_ids: set[str]
) -> list[dict[str, str]]:
    """Which observations an `unmanaged` glob exempts, and by which glob.

    An exemption withholds the report's question; it never withholds the
    observation. The triage has to see an exempted item to hold the line on
    something that runs code at login (SPEC.md section 5), and nothing can
    report on an exemption whose matches were discarded.

    A declared entry is never exempt. The two files can contradict each other,
    and the declaration is the more specific statement: dropping its evidence
    would leave drift reporting an installed asset as missing.

    `fnmatchcase` rather than `fnmatch`: matching a name is a governance
    decision, so it does not vary with the filesystem's case rules. Identical
    behaviour on both supported platforms, stated rather than inherited.
    """
    matches: list[dict[str, str]] = []
    for obs in observed:
        if obs.key in declared_ids:
            continue
        candidates = [c for c in (obs.key, obs.facts.get("path", "")) if c]
        glob = next(
            (
                g.glob
                for g in registry.unmanaged
                for c in candidates
                if fnmatch.fnmatchcase(c, g.glob)
            ),
            None,
        )
        if glob is not None:
            matches.append({"key": obs.key, "glob": glob})
    return matches


def unmanaged_globs(snapshot: dict[str, Any]) -> dict[str, str]:
    """Observed key -> the `unmanaged` glob that exempted it, read back from a
    snapshot. Rows that are not mappings of two strings (a hand-edit, an older
    schema) are skipped, so junk silences nothing."""
    return {
        row["key"]: row["glob"]
        for row in snapshot.get("unmanaged", []) or []
        if isinstance(row, dict)
        and isinstance(row.get("key"), str)
        and isinstance(row.get("glob"), str)
    }


def exemption_holds(glob: str | None, *, always_on: bool) -> bool:
    """Whether an `unmanaged` glob withholds the report's question about an
    observation.

    A glob that names one asset exactly is a decision about something the
    operator has looked at, so it holds for anything, including a service that
    starts itself. A glob carrying a metacharacter claims a name space instead,
    and a name space is something anything can enter by choosing its own name.
    So a pattern never covers a service that runs code at login: that is
    precisely the observation nobody has seen yet, and going quiet about it is
    the one failure this tool cannot afford.
    """
    if glob is None:
        return False
    return not always_on or not any(c in glob for c in "*?[")


def run_observe(
    repo_root: Path,
    *,
    attest: bool = False,
    now: datetime | None = None,
    platform: Platform | None = None,
    adapters: dict[str, Adapter] | None = None,
) -> dict[str, Any]:
    # Dependencies are injectable and default to the real platform and the
    # package-scanned adapters; tests pass controlled ones.
    now = now or datetime.now()
    platform = platform or current_platform()
    adapters = discover_adapters() if adapters is None else adapters

    registry_dir = repo_root / "registry"
    observed_dir = repo_root / "observed"
    host = platform.hostname()

    registry = load_registry(registry_dir)
    entries = registry.entries_for_host(host)

    out_path = snapshot_path(observed_dir, host)
    prior = _load_prior(out_path)

    ctx = Ctx(
        platform=platform,
        host=host,
        now=now,
        entries=entries,
        prior=prior,
        attest=attest,
        repo_root=repo_root,
        secrets=build_handle(repo_root),  # sealed: get() raises during observe
    )

    observed: list[Observed] = []
    failed: list[dict[str, str]] = []
    for name, adapter in adapters.items():
        try:
            produced = adapter.observe(ctx)
            # Checked here, at the source, so a fact that would silently do
            # nothing (a typo of a general one) or silently lie (a `present`
            # that is a string) fails as this adapter's scan rather than as a
            # missing alert nobody can trace back. It lands in `failed` with
            # the others, so one bad adapter still cannot sink the scan.
            for obs in produced:
                check_facts(obs.adapter, obs.native_id, obs.facts)
            observed.extend(produced)
        except Exception as exc:  # one bad adapter must not sink the whole scan
            failed.append({"adapter": name, "error": str(exc)})
    unmanaged = _unmanaged_matches(observed, registry, {e.id for e in entries})

    uncovered = sorted(registry.declared_adapters() - set(adapters))

    snapshot: dict[str, Any] = {
        "host": host,
        "ts": now.isoformat(),
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "engine_version": __version__,
        "observed": [o.to_dict() for o in observed],
        "unmanaged": unmanaged,
        "uncovered": uncovered,
        "failed": failed,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(out_path, json.dumps(snapshot, indent=2, sort_keys=False) + "\n")
    return snapshot
