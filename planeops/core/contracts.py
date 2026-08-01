"""Core wire types and the adapter/platform contracts (SPEC.md section 4).

Every interface here has a live implementer: `Adapter` (observe) is honored by
the manual and launchd adapters; `MutatingAdapter` (plan/execute) by launchd and
secrets, which `plane apply` drives. `Ctx.secrets` carries the redaction gate. The
usage contract is still deferred to its own milestone and is not declared yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TypeGuard, runtime_checkable

from planeops.core.schema import Entry
from planeops.secrets import SecretsHandle


@dataclass(frozen=True, slots=True)
class Observed:
    """One fact observed on the live machine. Read-only output of `observe()`."""

    adapter: str
    native_id: str
    facts: dict[str, Any]
    version: str | None = None

    @property
    def key(self) -> str:
        """Matches an Entry when this equals `entry.id`."""
        return f"{self.adapter}/{self.native_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "native_id": self.native_id,
            "facts": self.facts,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Observed:
        return cls(
            adapter=raw["adapter"],
            native_id=raw["native_id"],
            facts=raw.get("facts", {}),
            version=raw.get("version"),
        )


@runtime_checkable
class Platform(Protocol):
    """OS seam. One implementation per OS; the core imports only this contract."""

    name: str

    def hostname(self) -> str: ...

    def home(self) -> Path: ...


@dataclass(frozen=True, slots=True)
class Ctx:
    """Handles passed to adapters. Read-only during observe."""

    platform: Platform
    host: str
    now: datetime
    entries: tuple[Entry, ...] = ()
    prior: dict[str, Observed] = field(default_factory=dict)
    attest: bool = False
    repo_root: Path | None = None
    # Sealed during observe/plan, unsealed by the engine only for execute. None
    # when no secrets store is resolvable (e.g. no repo_root).
    secrets: SecretsHandle | None = None


@runtime_checkable
class Adapter(Protocol):
    """What every adapter declares: its identity and read-only observation.
    Mutation is a separate protocol an adapter opts into by implementing it."""

    name: str
    domains: tuple[str, ...]

    def observe(self, ctx: Ctx) -> list[Observed]: ...


ChangeKind = Literal["install", "configure", "remove", "patch"]


@dataclass(frozen=True, slots=True)
class Change:
    """A proposed mutation. `diff` is shown at confirmation; `action` is an
    adapter-opaque payload handed back to that adapter's `execute`."""

    entry_id: str
    kind: ChangeKind
    diff: str
    action: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Result:
    ok: bool
    detail: str = ""


@runtime_checkable
class MutatingAdapter(Adapter, Protocol):
    """An adapter that can converge its domain. `plan` is pure (proposes Changes
    from an entry, its observed state, and a read-only `ctx` for host/repo/secrets
    resolution); `execute` runs one confirmed Change. The engine owns confirmation
    between them, so an adapter never mutates unprompted. `ctx` is required: the
    engine always provides it, and an optional-`None` contract only invited
    None-guards in adapters for a case production never produces.

    `default_phase` is the converge order an unphased entry inherits (packages 2,
    config 3, models 4, secrets 5, services 6): part of the contract, so an
    adapter author gets a typed signal it exists instead of a duck-typed getattr."""

    default_phase: int

    def plan(self, entry: Entry, obs: Observed | None, ctx: Ctx) -> list[Change]: ...

    def execute(self, change: Change, ctx: Ctx) -> Result: ...


def can_apply(adapter: object) -> TypeGuard[MutatingAdapter]:
    """True when the adapter implements the mutation capability."""
    return isinstance(adapter, MutatingAdapter)
