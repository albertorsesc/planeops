"""Store resolution: discovery, selection by instance data, the leaf-declared
default, and loud unknowns. Knows no concrete store beyond asserting the shipped
default resolves."""

import pytest

from planeops.secrets import SecretsHandle, SecretsStore, SecretsStoreProvider
from planeops.secrets.resolve import build_handle, discover_stores, resolve_store


def test_discovers_providers_and_they_satisfy_the_contract():
    found = discover_stores()
    assert "sops" in found  # the shipped store
    for name, provider in found.items():
        assert isinstance(provider, SecretsStoreProvider)
        assert provider.name == name
        assert isinstance(provider.is_default, bool)


def test_exactly_one_shipped_default():
    defaults = [p for p in discover_stores().values() if p.is_default]
    assert len(defaults) == 1  # a second store must ship is_default=False


def test_no_selection_resolves_the_default(tmp_path):
    store = resolve_store(tmp_path)
    assert isinstance(store, SecretsStore)


def test_selection_by_name(tmp_path):
    (tmp_path / "instance.yaml").write_text("secrets:\n  store: sops\n")
    assert isinstance(resolve_store(tmp_path), SecretsStore)


def test_unknown_selection_is_loud(tmp_path):
    # A typo'd store name must never silently mean "no secrets governance".
    (tmp_path / "instance.yaml").write_text("secrets:\n  store: vaultofnope\n")
    with pytest.raises(LookupError, match="vaultofnope"):
        resolve_store(tmp_path)


def test_no_repo_root_resolves_nothing():
    assert resolve_store(None) is None
    assert build_handle(None) is None


def test_build_handle_is_presence_only(tmp_path):
    handle = build_handle(tmp_path)
    assert isinstance(handle, SecretsHandle)
    # An absent store file answers "not configured" rather than raising.
    assert handle.exists("anything") is False


def test_provider_config_is_nested_under_the_store_name(tmp_path):
    # Engine keys (store, allow_targets) and provider keys must not share one
    # namespace: each provider reads only its own sub-mapping.
    (tmp_path / "vault.sops.yaml").write_text("k: ENC[x]\nsops: {}\n")
    (tmp_path / "instance.yaml").write_text(
        "secrets:\n  store: sops\n  sops:\n    path: vault.sops.yaml\n"
    )
    store = resolve_store(tmp_path)
    assert store is not None and store.exists("k")


def test_legacy_flat_path_key_fails_with_the_migration_hint(tmp_path):
    # The pre-0.1.0 flat form (`secrets.path`) must not silently fall back to
    # the default path: loud, with the new home spelled out.
    (tmp_path / "instance.yaml").write_text(
        "secrets:\n  store: sops\n  path: vault.sops.yaml\n"
    )
    with pytest.raises(LookupError, match="secrets.path moved"):
        resolve_store(tmp_path)


def test_unknown_key_in_the_secrets_section_is_loud(tmp_path):
    (tmp_path / "instance.yaml").write_text("secrets:\n  stor: sops\n")
    with pytest.raises(LookupError, match="store"):
        resolve_store(tmp_path)
