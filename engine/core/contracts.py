"""Core wire types and the adapter/platform contracts (SPEC.md section 4).

M1 is observe-only, so this file declares only what observe/drift consume. The
mutation contract (`plan`/`execute`, `Change`, `Result`), the usage contract,
and phase ordering land with their first implementer in later milestones: the
engine carries no interface ahead of a consumer.

Secrets handles are deferred to M4; `Ctx` carries only the platform for now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

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
    Mutation and usage arrive as separate protocols in the milestone that
    implements them, never before."""

    name: str
    domains: tuple[str, ...]

    def observe(self, ctx: Ctx) -> list[Observed]: ...
