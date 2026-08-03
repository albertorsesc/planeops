import pytest

from planeops._run import RunResult
from planeops.providers import yaml
from planeops.secrets.stores.sops import DEFAULT_PATH, STORE, SopsStore

# A sops file: keys plaintext, values encrypted, plus the `sops` metadata block.
STORE_DOC = {
    "openrouter_api_key": "ENC[AES256_GCM,data:abc,type:str]",
    "anthropic_api_key": "ENC[AES256_GCM,data:def,type:str]",
    "sops": {"age": [{"recipient": "age1example"}], "version": "3.8.1"},
}


def _write_store(tmp_path):
    p = tmp_path / "secrets.sops.yaml"
    p.write_text(yaml.dump(STORE_DOC))
    return p


def test_exists_reads_keys_without_decrypting(tmp_path):
    b = SopsStore(_write_store(tmp_path))
    assert b.exists("openrouter_api_key")
    assert b.exists("anthropic_api_key")
    assert not b.exists("nonexistent_key")


def test_sops_metadata_block_is_not_a_secret(tmp_path):
    assert not SopsStore(_write_store(tmp_path)).exists("sops")


def test_missing_store_is_empty(tmp_path):
    b = SopsStore(tmp_path / "nope.yaml")
    assert not b.exists("anything")
    assert b.meta("anything") is None


def test_malformed_store_degrades_not_crashes(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("{ not: valid: yaml")
    assert not SopsStore(bad).exists("x")


def test_meta_present_for_configured_secret(tmp_path):
    assert SopsStore(_write_store(tmp_path)).meta("openrouter_api_key") == {
        "configured": True
    }


def test_get_decrypts_via_sops(tmp_path):
    calls = []
    timeouts = []

    def fake_run(cmd, *, timeout=30):
        calls.append(cmd)
        timeouts.append(timeout)
        return RunResult(0, "sk-secret-value\n", "")

    b = SopsStore(_write_store(tmp_path), run=fake_run)
    assert b.get("openrouter_api_key") == "sk-secret-value"  # trailing newline trimmed
    assert calls == [
        ["sops", "-d", "--extract", '["openrouter_api_key"]', str(b._store)]
    ]
    # Decrypt can wait on an age key / pinentry, but must not wedge an apply
    # forever: bounded, and above the 30s default.
    assert timeouts == [60]


def test_get_refuses_an_absent_key_without_shelling_out(tmp_path):
    called = False

    def fake_run(cmd):
        nonlocal called
        called = True
        return RunResult(0, "", "")

    b = SopsStore(_write_store(tmp_path), run=fake_run)
    with pytest.raises(KeyError):
        b.get("nonexistent_key")
    assert called is False


def test_get_raises_when_sops_fails(tmp_path):
    b = SopsStore(
        _write_store(tmp_path),
        run=lambda cmd, *, timeout=30: RunResult(1, "", "no key"),
    )
    with pytest.raises(RuntimeError):
        b.get("openrouter_api_key")


def test_get_refuses_a_name_that_cannot_be_safely_quoted(tmp_path):
    # The name is interpolated into the sops --extract expression; a quote or
    # control character could change what gets extracted. Refuse before any
    # shell-out.
    called = False

    def fake_run(cmd, *, timeout=30):
        nonlocal called
        called = True
        return RunResult(0, "", "")

    store = tmp_path / "s.yaml"
    store.write_text('bad"name: x\nbad\nline: y\n')
    b = SopsStore(store, run=fake_run)
    with pytest.raises(ValueError, match="safely"):
        b.get('bad"name')
    assert called is False


# ---- the provider face (discovery + construction) ----


def test_provider_declares_itself_the_default():
    assert STORE.name == "sops" and STORE.is_default is True


def test_provider_builds_from_the_instance_section(tmp_path):
    store = STORE.build(tmp_path, {})
    assert store._store == tmp_path / DEFAULT_PATH  # its own default path
    custom = STORE.build(tmp_path, {"path": "vault/other.yaml"})
    assert custom._store == tmp_path / "vault" / "other.yaml"


def test_a_plaintext_store_is_refused_not_blessed(tmp_path):
    # Walk two: a failed `sops -e` left the store plaintext and presence
    # reported configured=true with zero alerts, a secret sitting in cleartext
    # in a directory the docs say to git. A store without sops metadata (or
    # with values that are not ENC[...]) is a loud error, landing as a
    # failed-scan alert, never a quiet "configured".
    p = tmp_path / "secrets.sops.yaml"
    p.write_text("walk2-key: walk2-value\n")
    store = SopsStore(p)
    with pytest.raises(ValueError, match="not encrypted"):
        store.exists("walk2-key")


def test_a_partially_plaintext_store_is_refused(tmp_path):
    p = tmp_path / "secrets.sops.yaml"
    p.write_text("a: ENC[AES256_GCM,data:x]\nb: oops-plain\nsops:\n  version: '3'\n")
    with pytest.raises(ValueError, match="not encrypted"):
        SopsStore(p).exists("a")


def test_metadata_failure_does_not_get_the_identity_hint(tmp_path):
    # The SOPS_AGE_KEY_FILE hint on a "metadata not found" failure points the
    # user away from the real problem (the file is not a sops file).
    p = tmp_path / "secrets.sops.yaml"
    p.write_text("k: ENC[AES256_GCM,data:x]\nsops:\n  version: '3'\n")

    def run(cmd, timeout=None):
        return RunResult(1, "", "Error getting data key: sops metadata not found")

    store = SopsStore(p, run=run)
    with pytest.raises(RuntimeError) as e:
        store.get("k")
    assert "SOPS_AGE_KEY_FILE" not in str(e.value)


def test_identity_failure_keeps_the_hint(tmp_path):
    p = tmp_path / "secrets.sops.yaml"
    p.write_text("k: ENC[AES256_GCM,data:x]\nsops:\n  version: '3'\n")

    def run(cmd, timeout=None):
        return RunResult(1, "", "failed to load age identities")

    with pytest.raises(RuntimeError, match="SOPS_AGE_KEY_FILE"):
        SopsStore(p, run=run).get("k")
