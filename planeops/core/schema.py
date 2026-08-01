"""Entry schema: one entry is one managed asset.

Field reference is SPEC.md. `lifecycle` and `tolerance` are closed
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
    needs: tuple[str, ...] = ()  # ids of entries this one depends on
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
    except (ValueError, TypeError):
        # ValueError: not a member. TypeError: an unhashable value (a YAML list/map
        # where a scalar was expected) -> a clean SchemaError, never a raw traceback.
        allowed = ", ".join(m.value for m in cls)
        raise SchemaError(
            f"entry {entry_id!r}: {field_name}={value!r} is not one of: {allowed}"
        ) from None


_SECRET_REF_KEYS = frozenset({"ref", "injected_as"})


def _validate_secret_ref(ref: Any, entry_id: Any) -> None:
    """One `secrets` item: `{ref: secret://<backend>/<name>, injected_as:
    file:<path>#KEY}`. Checked at load, so a typo'd ref fails with the entry
    named instead of being silently skipped when the secrets adapter later
    scans for consumers. Only the file form exists; an env: target is rejected
    as unsupported rather than advertised and then silently dropped."""
    if not isinstance(ref, dict):
        raise SchemaError(f"entry {entry_id!r}: each secrets item must be a mapping")
    _reject_unknown_keys(ref, _SECRET_REF_KEYS, f"entry {entry_id!r} secrets item")
    uri = ref.get("ref")
    if not isinstance(uri, str) or not uri.startswith("secret://"):
        raise SchemaError(
            f"entry {entry_id!r}: secrets ref={uri!r} must be a "
            "'secret://<backend>/<name>' string"
        )
    injected = ref.get("injected_as")
    if injected is None:
        return
    if isinstance(injected, str) and injected.startswith("env:"):
        raise SchemaError(
            f"entry {entry_id!r}: injected_as={injected!r}: env: injection is "
            "not supported yet; use 'file:<path>#KEY'"
        )
    path, sep, key = (
        injected[len("file:") :].rpartition("#")
        if isinstance(injected, str) and injected.startswith("file:")
        else ("", "", "")
    )
    if not (sep and path and key):
        raise SchemaError(
            f"entry {entry_id!r}: injected_as={injected!r} must be 'file:<path>#KEY'"
        )


# The complete key set an entry may carry. A key outside it is a typo, and a
# typo'd OPTIONAL key silently meaning "use the default" is the worst failure
# mode a declarative tool can have (`tolerence: alert` quietly not escalating).
_ENTRY_KEYS = frozenset(
    {
        "id", "adapter", "domain", "lifecycle", "intent", "class", "scope",
        "hosts", "owner", "tolerance", "kill_criteria", "auth", "phase", "pin",
        "needs", "secrets", "desired", "data",
    }
)  # fmt: skip


def _reject_unknown_keys(
    raw: dict[str, Any], allowed: frozenset[str], context: str
) -> None:
    """Unknown keys fail loudly: a did-you-mean when one is close, the allowed
    set otherwise, so even a file that plain doesn't belong (nothing close to
    match) explains what WOULD be valid here."""
    import difflib

    for key in raw:
        if not isinstance(key, str) or key not in allowed:
            close = difflib.get_close_matches(str(key), allowed, n=1)
            if close:
                hint = f"; did you mean {close[0]!r}?"
            else:
                hint = f"; expected one of: {', '.join(sorted(allowed))}"
            raise SchemaError(f"{context}: unknown field {key!r}{hint}")


def _require_str(value: Any, field_name: str, entry_id: Any) -> str:
    if not isinstance(value, str) or not value:
        raise SchemaError(
            f"entry {entry_id!r}: {field_name}={value!r} must be a non-empty string"
        )
    return value


def entry_from_dict(raw: dict[str, Any]) -> Entry:
    """Build and validate one Entry from a registry mapping."""
    if not isinstance(raw, dict):
        raise SchemaError(f"entry must be a mapping, got {type(raw).__name__}")

    entry_id = raw.get("id")
    _reject_unknown_keys(raw, _ENTRY_KEYS, f"entry {entry_id or '<no id>'!r}")
    for required in ("id", "adapter", "domain", "lifecycle", "intent"):
        if not raw.get(required):
            raise SchemaError(
                f"entry {entry_id or '<no id>'!r}: missing required field {required!r}"
            )
    assert entry_id is not None  # guaranteed by the required-field check above
    for field_name in ("id", "adapter", "domain", "intent"):
        _require_str(raw[field_name], field_name, entry_id)

    scope = raw.get("scope", "machine")
    if not isinstance(scope, str) or (
        scope not in ("machine", "user") and not scope.startswith("project:")
    ):
        raise SchemaError(
            f"entry {entry_id!r}: scope={scope!r} must be "
            "'machine', 'user', or 'project:<abs-path>'"
        )

    hosts = raw.get("hosts", ["any"])
    if (
        not isinstance(hosts, list)
        or not hosts
        or not all(isinstance(h, str) and h for h in hosts)
    ):
        # A non-string host never matches a hostname: the entry would silently
        # never apply anywhere.
        raise SchemaError(
            f"entry {entry_id!r}: hosts must be a non-empty list of strings"
        )

    klass = _enum(Klass, raw.get("class", "recipe"), "class", entry_id)
    data = raw.get("data")
    if klass is Klass.data and not data:
        raise SchemaError(f"entry {entry_id!r}: class 'data' requires a 'data' block")

    needs = raw.get("needs", [])
    if not isinstance(needs, list) or not all(isinstance(n, str) and n for n in needs):
        raise SchemaError(
            f"entry {entry_id!r}: needs must be a list of entry ids (strings)"
        )

    secrets = raw.get("secrets", [])
    if not isinstance(secrets, list):
        raise SchemaError(f"entry {entry_id!r}: secrets must be a list of mappings")
    for ref in secrets:
        _validate_secret_ref(ref, entry_id)

    phase = raw.get("phase")
    # bool is an int subclass; `phase: true` is a typo, not phase 1. A string
    # phase used to load fine and then crash apply's phase sort.
    if phase is not None and (isinstance(phase, bool) or not isinstance(phase, int)):
        raise SchemaError(f"entry {entry_id!r}: phase={phase!r} must be an integer")

    pin = raw.get("pin")
    if pin is not None and not isinstance(pin, str):
        raise SchemaError(
            f"entry {entry_id!r}: pin={pin!r} must be a string "
            "(quote it: YAML reads 1.2 as a number)"
        )

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
        needs=tuple(needs),
        secrets=tuple(raw.get("secrets", ())),
        desired=raw.get("desired", {}) or {},
        data=data,
    )
