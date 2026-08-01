"""`plane apply`: converge confirmed changes, one at a time.

The engine, not the adapter, owns confirmation: for every Change an adapter
plans, a diff is rendered and a decision is taken (y/n/a) before `execute` is
called. There is no code path that mutates the machine without a rendered diff
and a yes (SPEC.md sections 4-5). Observe-only adapters are skipped.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from engine.core.contracts import (
    Adapter,
    Change,
    Ctx,
    Platform,
    Result,
    can_apply,
)
from engine.core.discovery import discover_adapters
from engine.core.observe import load_observed, load_snapshot
from engine.core.registry import load_registry
from engine.core.schema import Entry, Owner
from engine.secrets import SecretsHandle, SecretsStore, materialization_handle
from engine.secrets.resolve import resolve_store

# Returns 'y' (apply), 'n' (skip), or 'a' (apply this and the rest of its domain).
Confirm = Callable[[Change], str]

_UNPHASED = 1000  # entries without an explicit phase converge after phased ones


@dataclass(frozen=True, slots=True)
class Applied:
    change: Change
    executed: bool
    result: Result | None


def _append_journal(observed_dir: Path, host: str, now: datetime, a: Applied) -> None:
    """Append one immutable record beside the snapshot, the moment its change is
    decided. Per-record (not batched at the end of the run) so a crash mid-apply
    still leaves every already-executed mutation on the record, which is when
    the journal matters most. `actor` is reserved for a future operator/agent
    identity."""
    journal = observed_dir / host / "applied.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a") as fh:
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
    secrets_store: SecretsStore | None = None,
) -> list[Applied]:
    from engine.platform import current_platform

    platform = platform or current_platform()
    adapters = discover_adapters() if adapters is None else adapters
    confirm = confirm or prompt_confirm
    now = now or datetime.now()

    observed_dir = repo_root / "observed"
    snapshot = load_snapshot(observed_dir, platform.hostname())
    host = snapshot.get("host") or platform.hostname()
    observed_by_key = load_observed(snapshot)

    registry = load_registry(repo_root / "registry")
    # ctx sees the FULL host registry so an adapter can resolve cross-references
    # (e.g. secrets materialization scans consumers). Only `to_converge` is narrowed
    # by --id/--phase: filtering the ctx too would hide the consumers a --phase-5
    # secrets run must materialize into phase-6 services.
    all_entries = list(registry.entries_for_host(host))
    to_converge = all_entries
    if only_id is not None:
        to_converge = [e for e in to_converge if e.id == only_id]
        if not to_converge:
            # A typo'd --id must be loud: falling through to "no changes" reads
            # as "the machine is fine" when the id was simply wrong.
            raise LookupError(
                f"no registry entry with id {only_id!r} for host {host!r}"
            )
    if only_phase is not None:
        to_converge = [e for e in to_converge if e.phase == only_phase]

    def _phase_of(entry: Entry) -> int:
        # entry phase wins; else the adapter's contract-declared default; an
        # unbuilt or observe-only adapter's entries sort last (apply skips them).
        if entry.phase is not None:
            return entry.phase
        adapter = adapters.get(entry.adapter)
        if adapter is not None and can_apply(adapter):
            return adapter.default_phase
        return _UNPHASED

    # Stable sort, so registry order is preserved within a phase.
    to_converge = sorted(to_converge, key=_phase_of)

    store = secrets_store if secrets_store is not None else resolve_store(repo_root)
    ctx = Ctx(
        platform=platform,
        host=host,
        now=now,
        entries=tuple(all_entries),
        prior=observed_by_key,
        repo_root=repo_root,
        # Presence-only here (and for every non-secrets execute). The value-capable
        # handle is built per-execute below, and only for a secret-domain adapter.
        secrets=SecretsHandle(store) if store is not None else None,
    )
    auto_domains: set[str] = set()
    applied: list[Applied] = []

    def _record(a: Applied) -> None:
        applied.append(a)
        _append_journal(observed_dir, host, now, a)

    for entry in to_converge:
        adapter = adapters.get(entry.adapter)
        if adapter is None or not can_apply(adapter):
            continue  # observe-only or unbuilt: nothing to converge
        if entry.owner is Owner.human:
            continue  # human-owned: the plane observes and reports, never writes
        obs = observed_by_key.get(entry.id)
        try:
            changes = adapter.plan(entry, obs, ctx)
        except Exception as exc:  # a broken adapter must not abort the whole run
            _record(
                Applied(
                    Change(entry.id, "patch", f"plan failed: {exc}", {}),
                    False,
                    Result(ok=False, detail=str(exc)),
                )
            )
            continue
        # Only a secret-domain adapter's execute may obtain a value, and only if a
        # store resolved. Every other execute keeps the presence-only handle.
        may_materialize = store is not None and "secret" in adapter.domains
        for change in changes:
            if entry.domain in auto_domains:
                decision = "y"
            else:
                decision = confirm(change)
                if decision == "a":
                    auto_domains.add(entry.domain)
                    decision = "y"
            if decision == "y":
                exec_ctx = ctx
                if may_materialize and store is not None:
                    exec_ctx = replace(ctx, secrets=materialization_handle(store))
                try:
                    result = adapter.execute(change, exec_ctx)
                except Exception as exc:  # contain a crashing execute
                    result = Result(ok=False, detail=f"execute raised: {exc}")
                _record(Applied(change, True, result))
            else:
                _record(Applied(change, False, None))

    return applied
