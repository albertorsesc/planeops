"""Core wire types and the adapter/platform contracts (SPEC.md section 4).

The engine, not adapters, owns confirmation: `plan()` returns Change objects and
`execute()` is invoked per confirmed change. An adapter that implements neither is
observe-only (it reports coverage without being able to apply).

Secrets handles are deferred to M4; `Ctx` carries only the platform for now.
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


ChangeKind = Literal["install", "configure", "remove", "patch"]


@dataclass(frozen=True, slots=True)
class Change:
    """A proposed mutation. `diff` is shown at confirmation; `action` is opaque."""

    entry_id: str
    kind: ChangeKind
    diff: str
    action: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Result:
    ok: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Usage:
    last: datetime | None = None
    count: int | None = None


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
    interactive: bool = False


@runtime_checkable
class Adapter(Protocol):
    """Minimum an adapter must expose. `plan`/`execute`/`usage` are optional
    capabilities detected structurally (an adapter without them is observe-only)."""

    name: str
    domains: tuple[str, ...]
    default_phase: int

    def observe(self, ctx: Ctx) -> list[Observed]: ...


def can_apply(adapter: object) -> bool:
    """True when the adapter offers the full plan+execute pair."""
    return callable(getattr(adapter, "plan", None)) and callable(getattr(adapter, "execute", None))
