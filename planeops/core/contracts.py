"""Core wire types and the adapter/platform contracts (SPEC.md section 4).

Every interface here has a live implementer: `Adapter` (observe) is honored by
the manual and launchd adapters; `MutatingAdapter` (plan/execute) by launchd,
secrets, and mcp, which `plane apply` drives. `Ctx.secrets` carries the redaction
gate. The usage contract is still deferred to its own milestone and is not
declared yet.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TypeGuard, runtime_checkable

from planeops.core.facts import GENERAL, check_facts
from planeops.core.schema import Entry
from planeops.secrets import SecretsHandle


@dataclass(frozen=True, slots=True)
class Observed:
    """One fact observed on the live machine. Read-only output of `observe()`."""

    adapter: str
    native_id: str
    facts: dict[str, Any]
    version: str | None = None

    @classmethod
    def of(
        cls,
        adapter: str,
        native_id: str,
        *,
        version: str | None = None,
        present: bool | None = None,
        drifted: bool | None = None,
        always_on: bool | None = None,
        stale: bool | None = None,
        configured: bool | None = None,
        governed_by: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> Observed:
        """An observation whose general facts are named rather than spelled.

        The facts an adapter records are its own business except for the six
        the triage acts on, and those arrive here as arguments so that writing
        `alwayson=True` is an unexpected keyword argument the type checker
        reports at this line. Spelled into a dict it would be a legal fact that
        nothing reads, and the service it describes would go unmentioned.

        An argument left unset records no fact at all, which is how a domain
        says it has no opinion; `present=False` is the domain saying no. The
        rest of the domain's facts go through `detail` and are untouched.
        """
        general: dict[str, Any] = {
            "present": present,
            "drifted": drifted,
            "always_on": always_on,
            "stale": stale,
            "configured": configured,
            "governed_by": governed_by,
        }
        for name in GENERAL:
            if name in (detail or {}):
                raise ValueError(
                    f"{adapter}/{native_id}: pass the general fact {name!r} as "
                    f"an argument, not in `detail`, so a misspelling of it is "
                    f"an error rather than a fact nothing reads"
                )
        facts: dict[str, Any] = dict(detail or {})
        # `is not None` and not truthiness: `present=False` is the whole reason
        # the retired check can tell a departed service from an absent domain.
        facts.update({k: v for k, v in general.items() if v is not None})
        check_facts(adapter, native_id, facts)
        return cls(adapter=adapter, native_id=native_id, facts=facts, version=version)

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
    # The sys.platform prefixes this impl serves; selection reads it, so the
    # contract requires it rather than defaulting an undeclared attribute.
    sys_platforms: tuple[str, ...]

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
