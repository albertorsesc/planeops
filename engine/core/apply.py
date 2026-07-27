"""`plane apply`: converge confirmed changes, one at a time.

The engine, not the adapter, owns confirmation: for every Change an adapter
plans, a diff is rendered and a decision is taken (y/n/a) before `execute` is
called. There is no code path that mutates the machine without a rendered diff
and a yes (SPEC.md sections 4-5). Observe-only adapters are skipped.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from engine.core.contracts import (
    Adapter,
    Change,
    Ctx,
    Observed,
    Platform,
    Result,
    can_apply,
)
from engine.core.discovery import discover_adapters
from engine.core.observe import snapshot_path
from engine.core.registry import load_registry
from engine.core.schema import Owner

# Returns 'y' (apply), 'n' (skip), or 'a' (apply this and the rest of its domain).
Confirm = Callable[[Change], str]

_UNPHASED = 1000  # entries without an explicit phase converge after phased ones


@dataclass(frozen=True, slots=True)
class Applied:
    change: Change
    executed: bool
    result: Result | None


def _write_journal(
    observed_dir: Path, host: str, now: datetime, applied: list[Applied]
) -> None:
    """Append an immutable record of this apply run beside the snapshot: what was
    proposed, what executed, and the outcome. `actor` is reserved for a future
    operator/agent identity."""
    journal = observed_dir / host / "applied.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a") as fh:
        for a in applied:
            fh.write(
                json.dumps(
                    {
                        "ts": now.isoformat(),
                        "host": host,
                        "actor": None,
                        "entry_id": a.change.entry_id,
                        "kind": a.change.kind,
                        "diff": a.change.diff,
                        "executed": a.executed,
                        "ok": a.result.ok if a.result else None,
                        "detail": a.result.detail if a.result else None,
                    }
                )
                + "\n"
            )


def prompt_confirm(change: Change) -> str:
    print(change.diff)
    try:
        answer = input(
            f"apply {change.entry_id} [{change.kind}]? "
            "(y=yes / n=no / a=all in domain) "
        )
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
        raise FileNotFoundError(
            f"no snapshot at {snap_path}; run `plane observe` first"
        )

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
    # Converge in phase order (SPEC.md section 5); unphased entries go last. The
    # sort is stable, so registry order is preserved within a phase.
    entries.sort(key=lambda e: e.phase if e.phase is not None else _UNPHASED)

    ctx = Ctx(
        platform=platform,
        host=host,
        now=now,
        entries=tuple(entries),
        prior=observed_by_key,
        repo_root=repo_root,
    )
    auto_domains: set[str] = set()
    applied: list[Applied] = []

    for entry in entries:
        adapter = adapters.get(entry.adapter)
        if adapter is None or not can_apply(adapter):
            continue  # observe-only or unbuilt: nothing to converge
        if entry.owner is Owner.human:
            continue  # human-owned: the plane observes and reports, never writes
        obs = observed_by_key.get(entry.id)
        try:
            changes = adapter.plan(entry, obs, ctx)
        except Exception as exc:  # a broken adapter must not abort the whole run
            applied.append(
                Applied(
                    Change(entry.id, "patch", f"plan failed: {exc}", {}),
                    False,
                    Result(ok=False, detail=str(exc)),
                )
            )
            continue
        for change in changes:
            if entry.domain in auto_domains:
                decision = "y"
            else:
                decision = confirm(change)
                if decision == "a":
                    auto_domains.add(entry.domain)
                    decision = "y"
            if decision == "y":
                try:
                    result = adapter.execute(change, ctx)
                except Exception as exc:  # contain a crashing execute
                    result = Result(ok=False, detail=f"execute raised: {exc}")
                applied.append(Applied(change, True, result))
            else:
                applied.append(Applied(change, False, None))

    if applied:
        _write_journal(observed_dir, host, now, applied)
    return applied
