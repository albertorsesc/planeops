"""`plane apply`: converge confirmed changes, one at a time.

The engine, not the adapter, owns confirmation: for every Change an adapter
plans, a diff is rendered and a decision is taken (y/n/a) before `execute` is
called. There is no code path that mutates the machine without a rendered diff
and a yes (SPEC.md sections 4-5). Observe-only adapters are skipped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from engine.core.contracts import Adapter, Change, Ctx, Observed, Platform, Result, can_apply
from engine.core.discovery import discover_adapters
from engine.core.observe import snapshot_path
from engine.core.registry import load_registry

# Returns 'y' (apply), 'n' (skip), or 'a' (apply this and the rest of its domain).
Confirm = Callable[[Change], str]


@dataclass(frozen=True, slots=True)
class Applied:
    change: Change
    executed: bool
    result: Result | None


def prompt_confirm(change: Change) -> str:
    print(change.diff)
    try:
        answer = input(f"apply {change.entry_id} [{change.kind}]? (y=yes / n=no / a=all in domain) ")
    except EOFError:
        return "n"  # non-interactive: never mutate without an explicit yes
    answer = answer.strip().lower()
    return answer[:1] if answer else "n"


def run_apply(
    repo_root: Path,
    *,
    only_id: str | None = None,
    only_phase: int | None = None,
    platform: Platform | None = None,
    adapters: dict[str, Adapter] | None = None,
    confirm: Confirm | None = None,
    now: datetime | None = None,
) -> list[Applied]:
    from engine.platform import current_platform

    platform = platform or current_platform()
    adapters = discover_adapters() if adapters is None else adapters
    confirm = confirm or prompt_confirm
    now = now or datetime.now()

    observed_dir = repo_root / "observed"
    snap_path = snapshot_path(observed_dir, platform.hostname())
    if not snap_path.is_file():
        raise FileNotFoundError(f"no snapshot at {snap_path}; run `plane observe` first")

    snapshot = json.loads(snap_path.read_text())
    host = snapshot["host"]
    observed_by_key = {
        o.key: o for o in (Observed.from_dict(d) for d in snapshot.get("observed", []))
    }

    registry = load_registry(repo_root / "registry")
    entries = list(registry.entries_for_host(host))
    if only_id is not None:
        entries = [e for e in entries if e.id == only_id]
    if only_phase is not None:
        entries = [e for e in entries if e.phase == only_phase]

    ctx = Ctx(platform=platform, host=host, now=now, entries=tuple(entries), prior=observed_by_key)
    auto_domains: set[str] = set()
    applied: list[Applied] = []

    for entry in entries:
        adapter = adapters.get(entry.adapter)
        if adapter is None or not can_apply(adapter):
            continue  # observe-only or unbuilt: nothing to converge
        obs = observed_by_key.get(entry.id)
        for change in adapter.plan(entry, obs):
            if entry.domain in auto_domains:
                decision = "y"
            else:
                decision = confirm(change)
                if decision == "a":
                    auto_domains.add(entry.domain)
                    decision = "y"
            if decision == "y":
                applied.append(Applied(change, True, adapter.execute(change, ctx)))
            else:
                applied.append(Applied(change, False, None))

    return applied
