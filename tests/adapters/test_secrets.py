from datetime import datetime

from planeops.adapters.secrets import ADAPTER, SecretsAdapter
from planeops.core.contracts import Ctx, can_apply
from planeops.core.schema import entry_from_dict
from planeops.secrets import SecretsHandle, materialization_handle


class FakeBackend:
    name = "fake"

    def __init__(self, present):
        self._present = set(present)

    def exists(self, name):
        return name in self._present

    def meta(self, name):
        return {"configured": True} if name in self._present else None

    def get(self, name):
        # As strict as the real SopsStore: an unknown name raises rather than
        # minting a value, so a test can't silently materialize a nonexistent
        # secret and pass anyway.
        if name not in self._present:
            raise KeyError(f"secret {name!r} is not configured")
        return f"VALUE::{name}"


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


def _consumer(name, injected_as):
    return entry_from_dict(
        {
            "id": f"launchd/consumer-of-{name}",
            "adapter": "launchd",
            "domain": "service",
            "lifecycle": "active",
            "intent": "needs a secret injected",
            "secrets": [{"ref": f"secret://{name}", "injected_as": injected_as}],
        }
    )


class _Plat:
    """Minimal Platform stub: plan/execute receive a real ctx, per the contract.
    Home is a fixed fake path; every injection target in these tests is absolute,
    so nothing resolves against it."""

    name = "fake"

    def hostname(self):
        return "testhost"

    def home(self):
        from pathlib import Path

        return Path("/home/fake")


def _ctx(entries, repo_root=None, secrets=None):
    return Ctx(
        platform=_Plat(),
        host="testhost",
        now=datetime(2026, 7, 28),
        entries=tuple(entries),
        repo_root=repo_root,
        secrets=secrets,
    )


# ---- observe: presence only ----------------------------------------------


def test_observe_reports_presence_only():
    a = SecretsAdapter(store=FakeBackend(["openrouter"]))
    out = {
        o.native_id: o for o in a.observe(_ctx([_entry("openrouter"), _entry("gone")]))
    }
    assert out["openrouter"].facts == {"configured": True, "present": True}
    assert out["gone"].facts == {"configured": False, "present": False}
    assert out["openrouter"].key == "secrets/openrouter"


def test_observe_never_carries_a_value():
    o = SecretsAdapter(store=FakeBackend(["k"])).observe(_ctx([_entry("k")]))[0]
    assert set(o.facts) == {"configured", "present"} and o.version is None


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
    assert SecretsAdapter(store=FakeBackend([])).observe(_ctx([other])) == []


def test_default_backend_needs_a_repo_root():
    assert SecretsAdapter().observe(_ctx([_entry("k")])) == []


def test_default_store_resolves_at_the_instance_root(tmp_path):
    # The default store lives at the instance ROOT, never inside registry/
    # (registry files are strictly entries+globs; the store is not one).
    store = tmp_path / "secrets.sops.yaml"
    store.write_text("openrouter-api-key: ENC[data]\nsops:\n  version: '3'\n")
    out = {
        o.native_id: o
        for o in SecretsAdapter().observe(
            _ctx([_entry("openrouter-api-key"), _entry("absent")], repo_root=tmp_path)
        )
    }
    assert out["openrouter-api-key"].facts == {"configured": True, "present": True}
    assert out["absent"].facts == {"configured": False, "present": False}


def test_store_path_is_overridable_via_instance_yaml(tmp_path):
    store = tmp_path / "vault.sops.yaml"
    store.write_text("k: ENC[data]\nsops: {}\n")
    # `store` names the KIND (discovered); the store's own knobs nest under
    # its name, so provider keys never collide with engine keys.
    (tmp_path / "instance.yaml").write_text(
        "secrets:\n  store: sops\n  sops:\n    path: vault.sops.yaml\n"
    )
    out = SecretsAdapter().observe(_ctx([_entry("k")], repo_root=tmp_path))
    assert out[0].facts == {"configured": True, "present": True}


# ---- materialization ------------------------------------------------------


def test_secrets_can_materialize():
    assert can_apply(ADAPTER)


def test_plan_proposes_a_value_redacted_materialization(tmp_path):
    target = tmp_path / "env"
    consumer = _consumer("openrouter-api-key", f"file:{target}#OPENROUTER_API_KEY")
    secret = _entry("openrouter-api-key")
    changes = SecretsAdapter().plan(secret, None, _ctx([secret, consumer]))
    assert len(changes) == 1
    c = changes[0]
    assert c.entry_id == "secrets/openrouter-api-key"
    assert c.kind == "configure"
    assert "value redacted" in c.diff and "VALUE" not in c.diff
    assert c.action == {
        "name": "openrouter-api-key",
        "path": str(target),
        "key": "OPENROUTER_API_KEY",
    }


def test_plan_skips_an_already_materialized_key(tmp_path):
    target = tmp_path / "env"
    target.write_text("OPENROUTER_API_KEY=already-there\n")
    consumer = _consumer("openrouter-api-key", f"file:{target}#OPENROUTER_API_KEY")
    secret = _entry("openrouter-api-key")
    assert SecretsAdapter().plan(secret, None, _ctx([secret, consumer])) == []


def test_execute_writes_value_only_to_target_and_redacts_result(tmp_path):
    target = tmp_path / "svc" / "env"
    consumer = _consumer("openrouter-api-key", f"file:{target}#OPENROUTER_API_KEY")
    secret = _entry("openrouter-api-key")
    [change] = SecretsAdapter().plan(secret, None, _ctx([secret, consumer]))

    value = materialization_handle(FakeBackend(["openrouter-api-key"]))
    res = SecretsAdapter().execute(
        change, _ctx([secret, consumer], repo_root=tmp_path, secrets=value)
    )

    assert res.ok
    assert "VALUE" not in res.detail  # the result never carries the value
    assert (
        target.read_text() == "OPENROUTER_API_KEY=VALUE::openrouter-api-key\n"
    )  # the value lands only in the injection target
    assert target.stat().st_mode & 0o777 == 0o600


def test_execute_fails_closed_with_a_presence_only_handle(tmp_path):
    target = tmp_path / "env"
    consumer = _consumer("openrouter-api-key", f"file:{target}#K")
    secret = _entry("openrouter-api-key")
    [change] = SecretsAdapter().plan(secret, None, _ctx([secret, consumer]))

    presence = SecretsHandle(FakeBackend(["openrouter-api-key"]))  # get() raises
    res = SecretsAdapter().execute(
        change, _ctx([secret, consumer], repo_root=tmp_path, secrets=presence)
    )

    assert not res.ok
    assert not target.exists()  # a presence-only handle materializes nothing


def test_execute_refuses_a_symlinked_target(tmp_path):
    real = tmp_path / "real_secrets"
    real.write_text("PRE=existing\n")
    link = tmp_path / "env"
    link.symlink_to(real)  # a planted symlink at the injection path
    consumer = _consumer("openrouter-api-key", f"file:{link}#OPENROUTER_API_KEY")
    secret = _entry("openrouter-api-key")
    [change] = SecretsAdapter().plan(secret, None, _ctx([secret, consumer]))

    value = materialization_handle(FakeBackend(["openrouter-api-key"]))
    res = SecretsAdapter().execute(
        change, _ctx([secret, consumer], repo_root=tmp_path, secrets=value)
    )

    assert not res.ok  # refused
    assert real.read_text() == "PRE=existing\n"  # link target never written through


def test_execute_follows_a_legitimate_symlinked_parent(tmp_path):
    # A symlinked ANCESTOR that resolves to WITHIN an allowed base (e.g. macOS
    # /var -> /private/var) must still work, so real system paths are not broken.
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    link_dir = tmp_path / "link"
    link_dir.symlink_to(real_dir, target_is_directory=True)
    target = link_dir / "env"  # parent is a symlink to real_dir
    consumer = _consumer("openrouter-api-key", f"file:{target}#OPENROUTER_API_KEY")
    secret = _entry("openrouter-api-key")
    [change] = SecretsAdapter().plan(secret, None, _ctx([secret, consumer]))

    value = materialization_handle(FakeBackend(["openrouter-api-key"]))
    res = SecretsAdapter().execute(
        change, _ctx([secret, consumer], repo_root=tmp_path, secrets=value)
    )

    assert res.ok  # legitimate symlinked parent is followed
    assert (
        real_dir / "env"
    ).read_text() == "OPENROUTER_API_KEY=VALUE::openrouter-api-key\n"


def test_execute_appends_without_disturbing_other_keys(tmp_path):
    target = tmp_path / "env"
    target.write_text("KEEP=1\nOTHER=2\n")  # a different key already present
    consumer = _consumer("openrouter-api-key", f"file:{target}#OPENROUTER_API_KEY")
    secret = _entry("openrouter-api-key")
    [change] = SecretsAdapter().plan(secret, None, _ctx([secret, consumer]))

    value = materialization_handle(FakeBackend(["openrouter-api-key"]))
    SecretsAdapter().execute(
        change, _ctx([secret, consumer], repo_root=tmp_path, secrets=value)
    )

    lines = target.read_text().splitlines()
    assert "KEEP=1" in lines and "OTHER=2" in lines
    assert "OPENROUTER_API_KEY=VALUE::openrouter-api-key" in lines


def _materialize(tmp_path, target, *, repo_root, allow=None):
    """Drive one materialization to `target` and return the Result."""
    if allow is not None:
        (repo_root / "instance.yaml").write_text(
            "secrets:\n  allow_targets:\n" + "".join(f"    - {p}\n" for p in allow)
        )
    consumer = _consumer("openrouter-api-key", f"file:{target}#OPENROUTER_API_KEY")
    secret = _entry("openrouter-api-key")
    [change] = SecretsAdapter().plan(secret, None, _ctx([secret, consumer]))
    value = materialization_handle(FakeBackend(["openrouter-api-key"]))
    return SecretsAdapter().execute(
        change, _ctx([secret, consumer], repo_root=repo_root, secrets=value)
    )


def test_execute_refuses_a_target_outside_the_allowed_bases(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside" / "env"  # not under repo (or home)
    res = _materialize(tmp_path, outside, repo_root=repo)
    assert not res.ok and "allowed bases" in res.detail
    assert not outside.exists()


def test_execute_refuses_an_ancestor_symlink_that_escapes_the_bases(tmp_path):
    # A symlinked ancestor inside the repo pointing OUT of it must not
    # redirect the secret into the attacker directory.
    repo = tmp_path / "repo"
    repo.mkdir()
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    (repo / "link").symlink_to(attacker, target_is_directory=True)
    res = _materialize(tmp_path, repo / "link" / "env", repo_root=repo)
    assert not res.ok and "allowed bases" in res.detail
    assert not (attacker / "env").exists()  # nothing landed in the attacker dir


def test_allow_targets_extends_the_bases(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    extra = tmp_path / "extra"  # outside repo, explicitly allowlisted
    res = _materialize(tmp_path, extra / "env", repo_root=repo, allow=[str(extra)])
    assert res.ok
    assert (
        extra / "env"
    ).read_text() == "OPENROUTER_API_KEY=VALUE::openrouter-api-key\n"


def test_materialization_creates_missing_parents_private(tmp_path):
    # A secret lands under a parent that may not exist yet; that parent must be
    # created 0700, not at the process umask, or the 0600 on the file is
    # undermined by a listable directory.
    from planeops.adapters.secrets import _upsert_env

    parent = tmp_path / "new" / "nested"
    _upsert_env(parent, ".env", "KEY", "value")
    assert (parent / ".env").read_text() == "KEY=value\n"
    assert (tmp_path / "new").stat().st_mode & 0o777 == 0o700
    assert parent.stat().st_mode & 0o777 == 0o700


def test_observe_surfaces_undeclared_store_keys():
    # A key in the store that no entry declares is a shadow secret: it must
    # land in the snapshot so drift can call it ungoverned.
    class _Listing(FakeBackend):
        def keys(self):
            return self._present

    a = SecretsAdapter(store=_Listing(["declared-key", "shadow-key"]))
    out = a.observe(_ctx([_entry("declared-key")]))
    assert [o.native_id for o in out] == ["declared-key", "shadow-key"]
    assert all(o.facts["configured"] for o in out)


def test_observe_without_enumeration_stays_declared_only():
    out = SecretsAdapter(store=FakeBackend([])).observe(_ctx([_entry("only-declared")]))
    assert [o.native_id for o in out] == ["only-declared"]
    assert out[0].facts["configured"] is False
