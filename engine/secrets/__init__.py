"""Secrets backend contract and the redaction gate.

A backend reports whether a secret is CONFIGURED (`exists`/`meta`, presence only)
and can return a value (`get`). observe, plan, and every non-secrets execute are
handed a `SecretsHandle`: presence works, but `get()` always raises, and there is
no method on it that yields a value or a value-capable handle. The engine builds a
value-capable handle itself, from the backend, only for the secrets adapter's
execute (`materialization_handle`).

This is a guard-rail: a secret value cannot reach a snapshot, a report, or the
journal on the ordinary paths, and the obvious footgun (an "unseal me" method on
the handle an adapter already holds) does not exist. It is NOT an in-process
sandbox. Python cannot stop code that deliberately reaches a private attribute, so
the guarantee is "no value by construction on the ordinary paths", not
"unreachable by adversarial in-process code".
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SecretsBackend(Protocol):
    name: str

    def exists(self, name: str) -> bool:
        """Is this secret configured in the backend? Never decrypts a value."""
        ...

    def meta(self, name: str) -> dict[str, Any] | None:
        """Non-secret metadata (e.g. presence, rotation), or None if absent."""
        ...

    def get(self, name: str) -> str:
        """The decrypted value. Reached only through a materialization handle."""
        ...


class RedactionError(RuntimeError):
    """Raised when a secret value is requested outside the secrets adapter's
    execute (i.e. on any presence-only handle)."""


class SecretsHandle:
    """The presence-only handle placed on `ctx.secrets` for observe, plan, and
    every non-secrets execute. `exists`/`meta` answer presence; `get()` always
    raises. There is deliberately no `unsealed()` or any other method that returns
    a value-capable handle: materialization is the engine's job, not an adapter's."""

    def __init__(self, backend: SecretsBackend) -> None:
        self._backend = backend

    def exists(self, name: str) -> bool:
        return self._backend.exists(name)

    def meta(self, name: str) -> dict[str, Any] | None:
        return self._backend.meta(name)

    def get(self, name: str) -> str:
        raise RedactionError(
            f"secrets.get({name!r}) is not allowed here: a secret value is "
            "materialized only inside the secrets adapter's execute()"
        )


class _MaterializationHandle(SecretsHandle):
    """Value-capable handle. The engine builds this from the backend only for the
    secrets adapter's execute; it is never handed to observe or plan."""

    def get(self, name: str) -> str:
        return self._backend.get(name)


def materialization_handle(backend: SecretsBackend) -> SecretsHandle:
    """A value-capable handle over `backend`. Takes a backend, not a presence
    handle, so it cannot be turned against the handle an adapter already holds:
    only the engine (which resolves the backend) can call it."""
    return _MaterializationHandle(backend)
