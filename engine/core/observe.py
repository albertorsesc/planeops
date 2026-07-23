"""`plane observe`: run every adapter's read-only observe, write a snapshot.

Read-only and safe for the scheduled slot. Never mutates the machine.
"""

from __future__ import annotations

import fnmatch
import json
from datetime import datetime
from pathlib import Path

from engine import __version__
from engine.core.contracts import Ctx, Observed
from engine.core.discovery import discover_adapters
from engine.core.registry import Registry, load_registry
from engine.platform import current_platform


def snapshot_path(observed_dir: Path, host: str) -> Path:
    return observed_dir / host / "snapshot.json"


def _load_prior(path: Path) -> dict[str, Observed]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text())
    prior: dict[str, Observed] = {}
    for item in raw.get("observed", []):
        obs = Observed.from_dict(item)
        prior[obs.key] = obs
    return prior


def _drop_unmanaged(observed: list[Observed], registry: Registry) -> list[Observed]:
    if not registry.unmanaged:
        return observed
    patterns = [g.glob for g in registry.unmanaged]

    def managed(obs: Observed) -> bool:
        candidates = [obs.key, obs.facts.get("path", "")]
        return not any(
            fnmatch.fnmatch(c, p) for c in candidates if c for p in patterns
        )

    return [o for o in observed if managed(o)]


def run_observe(
    repo_root: Path,
    *,
    attest: bool = False,
    interactive: bool = False,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now()
    registry_dir = repo_root / "registry"
    observed_dir = repo_root / "observed"

    platform = current_platform()
    host = platform.hostname()

    registry = load_registry(registry_dir)
    entries = registry.entries_for_host(host)
    adapters = discover_adapters()

    out_path = snapshot_path(observed_dir, host)
    prior = _load_prior(out_path)

    ctx = Ctx(
        platform=platform,
        host=host,
        now=now,
        entries=entries,
        prior=prior,
        attest=attest,
        interactive=interactive,
    )

    observed: list[Observed] = []
    for adapter in adapters.values():
        observed.extend(adapter.observe(ctx))
    observed = _drop_unmanaged(observed, registry)

    uncovered = sorted(registry.declared_adapters() - set(adapters))

    snapshot = {
        "host": host,
        "ts": now.isoformat(),
        "engine_version": __version__,
        "observed": [o.to_dict() for o in observed],
        "uncovered": uncovered,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2, sort_keys=False) + "\n")
    return snapshot
