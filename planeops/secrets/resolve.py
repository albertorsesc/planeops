"""Resolve which secrets store serves this instance, knowing no concrete store.

Providers are discovered under `planeops/secrets/stores/` (module-level `STORE`),
the same package-scan seam adapters, importers, platforms, and schedulers use.
Selection is instance data: `instance.yaml`'s `secrets.store` names a provider;
with no selection, the provider that declares `is_default` wins, so even the
default is leaf knowledge, not resolution-layer knowledge. Swapping or adding a
store therefore never touches this module.

`build_handle` returns the presence-only handle for observe/plan; the
value-capable handle is built separately, from the store, only for the secrets
adapter's execute (see `planeops.secrets.materialization_handle`).
"""

from __future__ import annotations

from pathlib import Path

import planeops.secrets.stores
from planeops.config import section as instance_section
from planeops.secrets import SecretsHandle, SecretsStore, SecretsStoreProvider


def discover_stores() -> dict[str, SecretsStoreProvider]:
    """Every `planeops.secrets.stores.<mod>` exposing a `STORE` provider."""
    from planeops.core.discovery import discover

    return discover(
        planeops.secrets.stores,
        "STORE",
        SecretsStoreProvider,  # type: ignore[type-abstract]  # isinstance-only
    )


# Keys the ENGINE owns at the `secrets:` level; every other allowed key is the
# name of a discovered store kind holding that provider's own sub-mapping, so
# engine and provider settings can never collide in one namespace.
_ENGINE_KEYS = frozenset({"store", "allow_targets"})


def _check_section(
    section: dict[str, object], providers: dict[str, SecretsStoreProvider]
) -> None:
    if "path" in section:
        # The pre-0.1.0 flat form. Loud, with the new home spelled out.
        raise LookupError(
            "secrets.path moved: a store's own settings nest under the store's "
            "name, e.g. secrets: {store: <kind>, <kind>: {path: ...}}"
        )
    from planeops.core.schema import SchemaError, reject_unknown_keys

    try:
        reject_unknown_keys(
            section, _ENGINE_KEYS | frozenset(providers), "instance.yaml secrets"
        )
    except SchemaError as exc:
        raise LookupError(str(exc)) from None


def resolve_provider(repo_root: Path) -> SecretsStoreProvider | None:
    """The selected (or default) store PROVIDER for this instance. An unknown
    selection is a loud operator error, never a silent None."""
    section = instance_section(repo_root, "secrets")
    providers = discover_stores()
    _check_section(section, providers)
    selected = section.get("store")
    if isinstance(selected, str) and selected:
        provider = providers.get(selected)
        if provider is None:
            raise LookupError(
                f"unknown secrets store {selected!r}; available: "
                + ", ".join(sorted(providers))
            )
        return provider
    defaults = [p for p in providers.values() if p.is_default]
    if len(defaults) > 1:
        names = ", ".join(sorted(p.name for p in defaults))
        raise LookupError(f"multiple secrets stores claim default: {names}")
    return defaults[0] if defaults else None


def resolve_store(repo_root: Path | None) -> SecretsStore | None:
    """The selected (or default) store for this instance, or None without a
    root."""
    if repo_root is None:
        return None
    provider = resolve_provider(repo_root)
    if provider is None:
        return None
    section = instance_section(repo_root, "secrets")
    return provider.build(repo_root, _provider_section(section, provider))


def _provider_section(
    section: dict[str, object], provider: SecretsStoreProvider
) -> dict[str, object]:
    """A provider sees ONLY its own sub-mapping (`secrets.<name>`), never the
    engine keys beside it."""
    sub = section.get(provider.name)
    return sub if isinstance(sub, dict) else {}


def build_handle(repo_root: Path | None) -> SecretsHandle | None:
    """A presence-only handle over the resolved store, or None."""
    store = resolve_store(repo_root)
    return SecretsHandle(store) if store is not None else None
