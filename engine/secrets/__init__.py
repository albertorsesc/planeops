"""Secrets backend contract (SPEC.md section 4).

A backend reports whether a secret is CONFIGURED and its metadata. It never
returns a value during observe: presence-only by construction. Materialization
(`get`, injection at apply time) and the redaction gate are a later slice; this
contract is deliberately read-only-presence so no code path can leak a value yet.
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
