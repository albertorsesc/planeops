"""`plane observe`: run every adapter's read-only observe, write a snapshot.

Read-only and safe for the scheduled slot. Never mutates the machine.
"""

from __future__ import annotations

import fnmatch
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from engine import __version__
from engine.core.contracts import Adapter, Ctx, Observed, Platform
from engine.core.discovery import discover_adapters
from engine.core.registry import Registry, load_registry
from engine.core.statefile import atomic_write, read_json_file
from engine.platform import current_platform
from engine.secrets.store import build_handle

SNAPSHOT_SCHEMA_VERSION = 1  # bump when the snapshot / entry wire format changes


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


def _drop_unmanaged(observed: list[Observed], registry: Registry) -> list[Observed]:
    if not registry.unmanaged:
        return observed
    patterns = [g.glob for g in registry.unmanaged]

    def managed(obs: Observed) -> bool:
        candidates = [obs.key, obs.facts.get("path", "")]
        return not any(fnmatch.fnmatch(c, p) for c in candidates if c for p in patterns)

    return [o for o in observed if managed(o)]


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
            observed.extend(adapter.observe(ctx))
        except Exception as exc:  # one bad adapter must not sink the whole scan
            failed.append({"adapter": name, "error": str(exc)})
    observed = _drop_unmanaged(observed, registry)

    uncovered = sorted(registry.declared_adapters() - set(adapters))

    snapshot: dict[str, Any] = {
        "host": host,
        "ts": now.isoformat(),
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "engine_version": __version__,
        "observed": [o.to_dict() for o in observed],
        "uncovered": uncovered,
        "failed": failed,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(out_path, json.dumps(snapshot, indent=2, sort_keys=False) + "\n")
    return snapshot
