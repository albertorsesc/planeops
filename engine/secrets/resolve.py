"""Resolve which secrets store serves this instance, knowing no concrete store.

Providers are discovered under `engine/secrets/stores/` (module-level `STORE`),
the same package-scan seam adapters, importers, platforms, and schedulers use.
Selection is instance data: `instance.yaml`'s `secrets.store` names a provider;
with no selection, the provider that declares `is_default` wins, so even the
default is leaf knowledge, not resolution-layer knowledge. Swapping or adding a
store therefore never touches this module.

`build_handle` returns the presence-only handle for observe/plan; the
value-capable handle is built separately, from the store, only for the secrets
adapter's execute (see `engine.secrets.materialization_handle`).
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import engine.secrets.stores
from engine.config import section as instance_section
from engine.secrets import SecretsHandle, SecretsStore, SecretsStoreProvider


def discover_stores() -> dict[str, SecretsStoreProvider]:
    """Every `engine.secrets.stores.<mod>` exposing a `STORE` provider."""
    found: dict[str, SecretsStoreProvider] = {}
    for info in pkgutil.iter_modules(engine.secrets.stores.__path__):
        module = importlib.import_module(f"engine.secrets.stores.{info.name}")
        provider = getattr(module, "STORE", None)
        if provider is None:
            continue
        if not isinstance(provider, SecretsStoreProvider):
            raise TypeError(
                f"engine.secrets.stores.{info.name}.STORE does not satisfy "
                "the SecretsStoreProvider contract"
            )
        found[provider.name] = provider
    return found


def resolve_store(repo_root: Path | None) -> SecretsStore | None:
    """The selected (or default) store for this instance, or None without a
    root. An unknown selection is a loud operator error, never a silent None."""
    if repo_root is None:
        return None
    section = instance_section(repo_root, "secrets")
    providers = discover_stores()
    selected = section.get("store")
    if isinstance(selected, str) and selected:
        provider = providers.get(selected)
        if provider is None:
            raise LookupError(
                f"unknown secrets store {selected!r}; available: "
                + ", ".join(sorted(providers))
            )
        return provider.build(repo_root, section)
    defaults = [p for p in providers.values() if p.is_default]
    if len(defaults) > 1:
        names = ", ".join(sorted(p.name for p in defaults))
        raise LookupError(f"multiple secrets stores claim default: {names}")
    return defaults[0].build(repo_root, section) if defaults else None


def build_handle(repo_root: Path | None) -> SecretsHandle | None:
    """A presence-only handle over the resolved store, or None."""
    store = resolve_store(repo_root)
    return SecretsHandle(store) if store is not None else None
