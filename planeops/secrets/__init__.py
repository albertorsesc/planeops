"""Secrets store contracts and the redaction gate.

A store reports whether a secret is CONFIGURED (`exists`/`meta`, presence only)
and can return a value (`get`). observe, plan, and every non-secrets execute are
handed a `SecretsHandle`: presence works, but `get()` always raises, and there is
no method on it that yields a value or a value-capable handle. The engine builds a
value-capable handle itself, from the store, only for the secrets adapter's
execute (`materialization_handle`).

Store implementations live under `planeops/secrets/stores/`, one module per kind,
each exposing a module-level `STORE` provider, discovered by package scan like
every other seam: the resolution layer (`planeops/secrets/resolve.py`) knows no
concrete store, so swapping or adding one never touches it.

This is a guard-rail: a secret value cannot reach a snapshot, a report, or the
journal on the ordinary paths, and the obvious footgun (an "unseal me" method on
the handle an adapter already holds) does not exist. It is NOT an in-process
sandbox. Python cannot stop code that deliberately reaches a private attribute, so
the guarantee is "no value by construction on the ordinary paths", not
"unreachable by adversarial in-process code".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SecretsStore(Protocol):
    name: str

    def exists(self, name: str) -> bool:
        """Is this secret configured in the store? Never decrypts a value."""
        ...

    def meta(self, name: str) -> dict[str, Any] | None:
        """Non-secret metadata (e.g. presence, rotation), or None if absent."""
        ...

    def get(self, name: str) -> str:
        """The decrypted value. Reached only through a materialization handle."""
        ...


@runtime_checkable
class BootstrapsStore(Protocol):
    """A provider that can create its own store from nothing (ISP: separate
    from SecretsStoreProvider so a store kind without self-bootstrap is simply
    not an instance of this). Both methods are cwd-proof by contract: any
    tool the provider shells to receives explicit paths/config, never relying
    on the working directory."""

    def bootstrap_preview(
        self, repo_root: Path, *, age_key_file: Path | None
    ) -> list[str]:
        """What bootstrap WOULD write, for the confirm prompt."""
        ...

    def bootstrap(self, repo_root: Path, *, age_key_file: Path | None) -> list[str]:
        """Create identity (if missing), rules, and the encrypted store.
        Returns the actions taken. Raises LookupError if a store already
        exists (re-init must be a deliberate, manual act)."""
        ...


@runtime_checkable
class EnumeratesKeys(Protocol):
    """A store that can list its key NAMES (presence-level, never values), so
    observe can surface a key nobody declared the same way it surfaces an
    ungoverned service (ISP: a store kind whose backend forbids listing is
    simply not an instance)."""

    def keys(self) -> set[str]:
        """Every secret name in the store. Never decrypts a value."""
        ...


@runtime_checkable
class RemovesValues(Protocol):
    """A store that can delete one value (ISP: separate from `AcceptsValues`
    so either capability can exist without the other)."""

    def remove_preview(self, name: str) -> list[str]:
        """What `remove` WOULD do, for the confirm prompt."""
        ...

    def remove_value(self, name: str) -> str:
        """Delete `name` from the store. Raises LookupError if it is not
        configured. Returns the action line for the terminal."""
        ...


@runtime_checkable
class AcceptsValues(Protocol):
    """A store that can write one value safely (ISP: separate from
    `SecretsStore` so a read-only store kind is simply not an instance).
    The contract every implementation must keep: the value never appears on
    a command line or in the environment of any spawned process, and any
    on-disk plaintext is transient, owner-only (0600), and destroyed before
    the method returns."""

    def ready(self) -> bool:
        """Does the store exist on disk, i.e. can `add_value` succeed? False
        lets the CLI offer the store's own bootstrap before asking for a
        value, instead of failing after the value was already typed."""
        ...

    def add_preview(self, name: str) -> list[str]:
        """What `add` WOULD do (add vs rotate, and where), for the prompt."""
        ...

    def add_value(self, name: str, value: str, *, force: bool) -> str:
        """Encrypt `value` under `name` into the store. Refuses an existing
        name unless `force` (rotation must be deliberate). Returns the action
        line for the terminal; the line never carries the value."""
        ...


@runtime_checkable
class SecretsStoreProvider(Protocol):
    """What a module under `planeops/secrets/stores/` exposes as `STORE`: enough
    for the resolution layer to select and construct the store without knowing
    what it is. `is_default` lives on the leaf, so even the default choice is
    the provider's own declaration, not resolution-layer knowledge."""

    name: str
    is_default: bool

    def build(self, repo_root: Path, section: dict[str, Any]) -> SecretsStore:
        """Construct the store for this instance. `section` is this provider's
        OWN sub-mapping (`secrets.<name>` in `instance.yaml`), never the whole
        `secrets:` block, so provider keys cannot collide with engine keys."""
        ...


class RedactionError(RuntimeError):
    """Raised when a secret value is requested outside the secrets adapter's
    execute (i.e. on any presence-only handle)."""


class SecretsHandle:
    """The presence-only handle placed on `ctx.secrets` for observe, plan, and
    every non-secrets execute. `exists`/`meta` answer presence; `get()` always
    raises. There is deliberately no `unsealed()` or any other method that returns
    a value-capable handle: materialization is the engine's job, not an adapter's."""

    def __init__(self, store: SecretsStore) -> None:
        self._store = store

    def exists(self, name: str) -> bool:
        return self._store.exists(name)

    def meta(self, name: str) -> dict[str, Any] | None:
        return self._store.meta(name)

    def keys(self) -> set[str] | None:
        """Every secret NAME in the store (presence-level, allowed on this
        handle), or None when the store kind cannot enumerate."""
        if isinstance(self._store, EnumeratesKeys):
            return self._store.keys()
        return None

    def get(self, name: str) -> str:
        raise RedactionError(
            f"secrets.get({name!r}) is not allowed here: a secret value is "
            "materialized only inside the secrets adapter's execute()"
        )


class _MaterializationHandle(SecretsHandle):
    """Value-capable handle. The engine builds this from the store only for the
    secrets adapter's execute; it is never handed to observe or plan."""

    def get(self, name: str) -> str:
        return self._store.get(name)


def materialization_handle(store: SecretsStore) -> SecretsHandle:
    """A value-capable handle over `store`. Takes a store, not a presence
    handle, so it cannot be turned against the handle an adapter already holds:
    only the engine (which resolves the store) can call it."""
    return _MaterializationHandle(store)
