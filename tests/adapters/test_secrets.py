from datetime import datetime

from engine.adapters.secrets import ADAPTER, SecretsAdapter
from engine.core.contracts import Ctx, can_apply
from engine.core.schema import entry_from_dict


class FakeBackend:
    name = "fake"

    def __init__(self, present):
        self._present = set(present)

    def exists(self, name):
        return name in self._present

    def meta(self, name):
        return {"configured": True} if name in self._present else None


def _entry(name):
    return entry_from_dict(
        {
            "id": f"secrets/{name}",
            "adapter": "secrets",
            "domain": "secret",
            "lifecycle": "active",
            "intent": "i",
        }
    )


def _ctx(entries, repo_root=None):
    return Ctx(
        platform=None,
        host="testhost",
        now=datetime(2026, 7, 27),
        entries=tuple(entries),
        repo_root=repo_root,
    )


def test_observe_reports_presence_only():
    a = SecretsAdapter(backend=FakeBackend(["openrouter"]))
    out = {
        o.native_id: o for o in a.observe(_ctx([_entry("openrouter"), _entry("gone")]))
    }
    assert out["openrouter"].facts == {"configured": True}
    assert out["gone"].facts == {"configured": False}
    assert out["openrouter"].key == "secrets/openrouter"


def test_observe_never_carries_a_value():
    o = SecretsAdapter(backend=FakeBackend(["k"])).observe(_ctx([_entry("k")]))[0]
    assert set(o.facts) == {"configured"} and o.version is None


def test_ignores_non_secret_entries():
    other = entry_from_dict(
        {
            "id": "manual/x",
            "adapter": "manual",
            "domain": "host",
            "lifecycle": "active",
            "intent": "i",
        }
    )
    assert SecretsAdapter(backend=FakeBackend([])).observe(_ctx([other])) == []


def test_secrets_is_observe_only():
    assert not can_apply(ADAPTER)


def test_default_backend_needs_a_repo_root():
    assert SecretsAdapter().observe(_ctx([_entry("k")])) == []


def test_default_backend_resolves_the_registry_store(tmp_path):
    # No injected backend and no instance.yaml: the default sops store path.
    store = tmp_path / "registry" / "secrets.sops.yaml"
    store.parent.mkdir(parents=True)
    store.write_text("openrouter-api-key: ENC[data]\nsops:\n  version: '3'\n")
    out = {
        o.native_id: o
        for o in SecretsAdapter().observe(
            _ctx([_entry("openrouter-api-key"), _entry("absent")], repo_root=tmp_path)
        )
    }
    assert out["openrouter-api-key"].facts == {"configured": True}
    assert out["absent"].facts == {"configured": False}


def test_store_path_is_overridable_via_instance_yaml(tmp_path):
    store = tmp_path / "vault.sops.yaml"
    store.write_text("k: ENC[data]\nsops: {}\n")
    (tmp_path / "instance.yaml").write_text("secrets:\n  store: vault.sops.yaml\n")
    out = SecretsAdapter().observe(_ctx([_entry("k")], repo_root=tmp_path))
    assert out[0].facts == {"configured": True}
