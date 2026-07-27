"""Entry schema: one entry is one managed asset.

Field reference is SPEC.md section 2. `lifecycle` and `tolerance` are closed
core vocabularies the engine reasons about; `domain` is an open set owned by
adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SchemaError(ValueError):
    """A registry entry violated the schema."""


class Lifecycle(StrEnum):
    active = "active"
    maintain = "maintain"
    parked = "parked"
    retired = "retired"
    purge = "purge"


class Tolerance(StrEnum):
    auto = "auto"
    report = "report"
    alert = "alert"


class Klass(StrEnum):
    recipe = "recipe"
    data = "data"
    cache = "cache"


class Owner(StrEnum):
    plane = "plane"
    runtime = "runtime"
    human = "human"


class Auth(StrEnum):
    none = "none"
    interactive = "interactive"


# Lifecycles that should be present on the machine vs. absent from it.
PRESENT_LIFECYCLES = frozenset({Lifecycle.active, Lifecycle.maintain, Lifecycle.parked})
ABSENT_LIFECYCLES = frozenset({Lifecycle.retired, Lifecycle.purge})


@dataclass(frozen=True, slots=True)
class Entry:
    """A declared desired-state entry. Immutable once loaded."""

    id: str
    adapter: str
    domain: str
    lifecycle: Lifecycle
    intent: str
    klass: Klass = Klass.recipe
    scope: str = "machine"
    hosts: tuple[str, ...] = ("any",)
    owner: Owner = Owner.runtime
    tolerance: Tolerance = Tolerance.report
    kill_criteria: str | None = None
    auth: Auth = Auth.none
    phase: int | None = None
    pin: str | None = None
    secrets: tuple[dict[str, Any], ...] = ()
    desired: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] | None = None

    @property
    def native_id(self) -> str:
        """The part of the id after the `<adapter>/` prefix, if present."""
        return self.id.split("/", 1)[1] if "/" in self.id else self.id

    def applies_to_host(self, host: str) -> bool:
        return "any" in self.hosts or host in self.hosts


def _enum[E: StrEnum](cls: type[E], value: Any, field_name: str, entry_id: str) -> E:
    try:
        return cls(value)
    except ValueError:
        allowed = ", ".join(m.value for m in cls)
        raise SchemaError(
            f"entry {entry_id!r}: {field_name}={value!r} is not one of: {allowed}"
        ) from None


def entry_from_dict(raw: dict[str, Any]) -> Entry:
    """Build and validate one Entry from a registry mapping."""
    if not isinstance(raw, dict):
        raise SchemaError(f"entry must be a mapping, got {type(raw).__name__}")

    entry_id = raw.get("id")
    for required in ("id", "adapter", "domain", "lifecycle", "intent"):
        if not raw.get(required):
            raise SchemaError(
                f"entry {entry_id or '<no id>'!r}: missing required field {required!r}"
            )
    assert entry_id is not None  # guaranteed by the required-field check above

    scope = raw.get("scope", "machine")
    if scope not in ("machine", "user") and not scope.startswith("project:"):
        raise SchemaError(
            f"entry {entry_id!r}: scope={scope!r} must be "
            "'machine', 'user', or 'project:<abs-path>'"
        )

    hosts = raw.get("hosts", ["any"])
    if not isinstance(hosts, list) or not hosts:
        raise SchemaError(f"entry {entry_id!r}: hosts must be a non-empty list")

    klass = _enum(Klass, raw.get("class", "recipe"), "class", entry_id)
    data = raw.get("data")
    if klass is Klass.data and not data:
        raise SchemaError(f"entry {entry_id!r}: class 'data' requires a 'data' block")

    return Entry(
        id=entry_id,
        adapter=raw["adapter"],
        domain=raw["domain"],
        lifecycle=_enum(Lifecycle, raw["lifecycle"], "lifecycle", entry_id),
        intent=raw["intent"],
        klass=klass,
        scope=scope,
        hosts=tuple(hosts),
        owner=_enum(Owner, raw.get("owner", "runtime"), "owner", entry_id),
        tolerance=_enum(
            Tolerance, raw.get("tolerance", "report"), "tolerance", entry_id
        ),
        kill_criteria=raw.get("kill_criteria"),
        auth=_enum(Auth, raw.get("auth", "none"), "auth", entry_id),
        phase=raw.get("phase"),
        pin=raw.get("pin"),
        secrets=tuple(raw.get("secrets", ())),
        desired=raw.get("desired", {}) or {},
        data=data,
    )
