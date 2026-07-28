"""Resolve the secrets store and build the presence handle the engine puts on `Ctx`.

The store path comes from `instance.yaml`'s `secrets.store` (default
`registry/secrets.sops.yaml`). `build_handle` returns a presence-only handle for
observe/plan; the value-capable handle is built separately, from the backend, only
for the secrets adapter's execute (see `engine.secrets.materialization_handle`).
"""

from __future__ import annotations

from pathlib import Path

from engine.config import section as instance_section
from engine.secrets import SecretsBackend, SecretsHandle
from engine.secrets.sops import SopsBackend

DEFAULT_STORE = "registry/secrets.sops.yaml"


def resolve_store_path(repo_root: Path | None) -> Path | None:
    if repo_root is None:
        return None
    configured = instance_section(repo_root, "secrets").get("store")
    rel = configured if isinstance(configured, str) and configured else DEFAULT_STORE
    return repo_root / rel


def resolve_backend(repo_root: Path | None) -> SecretsBackend | None:
    """The sops backend for the resolved store, or None if none resolves."""
    path = resolve_store_path(repo_root)
    return SopsBackend(path) if path is not None else None


def build_handle(repo_root: Path | None) -> SecretsHandle | None:
    """A presence-only handle over the resolved sops store, or None."""
    backend = resolve_backend(repo_root)
    return SecretsHandle(backend) if backend is not None else None
