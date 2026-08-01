"""Store resolution: instance.yaml's `secrets.store` decides the sops path; the
presence handle is built over it; no root means no store."""

from engine.secrets import SecretsHandle
from engine.secrets.sops import SopsBackend
from engine.secrets.store import (
    DEFAULT_STORE,
    build_handle,
    resolve_backend,
    resolve_store_path,
)


def test_default_store_path_under_the_repo(tmp_path):
    assert resolve_store_path(tmp_path) == tmp_path / DEFAULT_STORE


def test_instance_yaml_overrides_the_store_path(tmp_path):
    (tmp_path / "instance.yaml").write_text("secrets:\n  store: vault/other.yaml\n")
    assert resolve_store_path(tmp_path) == tmp_path / "vault" / "other.yaml"


def test_no_repo_root_resolves_nothing():
    assert resolve_store_path(None) is None
    assert resolve_backend(None) is None
    assert build_handle(None) is None


def test_build_handle_is_presence_only_over_a_sops_backend(tmp_path):
    handle = build_handle(tmp_path)
    assert isinstance(handle, SecretsHandle)
    backend = resolve_backend(tmp_path)
    assert isinstance(backend, SopsBackend)
    # An absent store answers "not configured" rather than raising.
    assert handle.exists("anything") is False
