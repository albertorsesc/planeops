"""Core wire types and the adapter/platform contracts (SPEC.md section 4).

Every interface here has a live implementer: `Adapter` (observe) is honored by
the manual and launchd adapters; `MutatingAdapter` (plan/execute) by launchd,
which `plane apply` drives. The usage contract and secrets handles are still
deferred to their own milestones and are therefore not declared yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from engine.core.schema import Entry


@dataclass(frozen=True, slots=True)
class Observed:
    """One fact observed on the live machine. Read-only output of `observe()`."""

    adapter: str
    native_id: str
    facts: dict
    version: str | None = None

    @property
    def key(self) -> str:
        """Matches an Entry when this equals `entry.id`."""
        return f"{self.adapter}/{self.native_id}"

    def to_dict(self) -> dict:
        return {
            "adapter": self.adapter,
            "native_id": self.native_id,
            "facts": self.facts,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Observed:
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
    action: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Result:
    ok: bool
    detail: str = ""


@runtime_checkable
class MutatingAdapter(Adapter, Protocol):
    """An adapter that can converge its domain. `plan` is pure (proposes
    Changes from an entry and its observed state); `execute` runs one confirmed
    Change. The engine owns confirmation between them, so an adapter never
    mutates unprompted."""

    def plan(self, entry: Entry, obs: Observed | None) -> list[Change]: ...

    def execute(self, change: Change, ctx: Ctx) -> Result: ...


def can_apply(adapter: object) -> bool:
    """True when the adapter implements the mutation capability."""
    return isinstance(adapter, MutatingAdapter)
