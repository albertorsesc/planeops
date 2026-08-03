from pathlib import Path

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
    # A failed `sops -e` can leave the store plaintext; presence must not
    # report configured=true with zero alerts over a secret sitting in
    # cleartext in a directory the docs say to git. A store without sops
    # metadata (or with values that are not ENC[...]) is a loud error, landing
    # as a failed-scan alert, never a quiet "configured".
    p = tmp_path / "secrets.sops.yaml"
    p.write_text("plain-key: plain-value\n")
    store = SopsStore(p)
    with pytest.raises(ValueError, match="not encrypted"):
        store.exists("plain-key")


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


# ---- add_value: one value in, encrypted, never on argv ----


def _rules(tmp_path):
    r = tmp_path / ".sops.yaml"
    r.write_text(
        "creation_rules:\n  - path_regex: secrets\\.sops\\.yaml$\n    age: age1x\n"
    )
    return r


def _add_runner(decrypt_out="{}\n", encrypt_ok=True, encrypt_writes=True, calls=None):
    """Stands in for sops: `-d` returns `decrypt_out`; `-e -i` re-writes the
    target with ENC[...] values plus the metadata block, like real sops."""

    def run(cmd, timeout=None):
        if calls is not None:
            calls.append(list(cmd))
        if cmd[:2] == ["sops", "-d"]:
            return RunResult(0, decrypt_out, "")
        if cmd[0] == "sops" and "-e" in cmd:
            if not encrypt_ok:
                return RunResult(1, "", "encrypt boom")
            target = Path(cmd[-1])
            if encrypt_writes:
                data = yaml.load(target.read_text()) or {}
                enc = {k: f"ENC[AES256_GCM,data:{k}]" for k in data}
                enc["sops"] = {"version": "3"}
                target.write_text(yaml.dump(enc))
            return RunResult(0, "", "")
        return RunResult(127, "", f"{cmd[0]}: not found")

    return run


def test_add_value_encrypts_into_the_store(tmp_path):
    _rules(tmp_path)
    store = SopsStore(
        _write_store(tmp_path),
        run=_add_runner(decrypt_out="openrouter_api_key: v1\nanthropic_api_key: v2\n"),
    )
    out = store.add_value("telegram_token", "hunter2", force=False)
    assert "added" in out and "hunter2" not in out
    text = (tmp_path / "secrets.sops.yaml").read_text()
    assert "telegram_token" in text and "hunter2" not in text
    assert "ENC[" in text and "sops" in text


def test_add_value_never_puts_the_value_on_argv(tmp_path):
    _rules(tmp_path)
    calls: list[list[str]] = []
    store = SopsStore(_write_store(tmp_path), run=_add_runner(calls=calls))
    store.add_value("k1", "super-secret-value", force=False)
    for cmd in calls:
        assert all("super-secret-value" not in arg for arg in cmd), cmd


def test_add_value_leaves_no_plaintext_behind(tmp_path):
    _rules(tmp_path)
    store = SopsStore(_write_store(tmp_path), run=_add_runner())
    store.add_value("k1", "sekrit", force=False)
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".plane-secrets-")]
    assert leftovers == []
    for p in tmp_path.rglob("*"):
        if p.is_file():
            assert "sekrit" not in p.read_text()


def test_add_value_refuses_an_existing_name_without_force(tmp_path):
    _rules(tmp_path)
    store = SopsStore(_write_store(tmp_path), run=_add_runner())
    with pytest.raises(LookupError, match="--force"):
        store.add_value("openrouter_api_key", "v", force=False)


def test_add_value_rotates_with_force(tmp_path):
    _rules(tmp_path)
    store = SopsStore(
        _write_store(tmp_path),
        run=_add_runner(decrypt_out="openrouter_api_key: old\nanthropic_api_key: v2\n"),
    )
    out = store.add_value("openrouter_api_key", "new", force=True)
    assert "rotated" in out and "new" not in out.split("'")[0]


def test_add_value_requires_a_bootstrapped_store(tmp_path):
    with pytest.raises(LookupError, match="secrets init"):
        SopsStore(tmp_path / "secrets.sops.yaml", run=_add_runner()).add_value(
            "k", "v", force=False
        )
    _write_store(tmp_path)  # store exists, rules missing
    with pytest.raises(LookupError, match="secrets init"):
        SopsStore(tmp_path / "secrets.sops.yaml", run=_add_runner()).add_value(
            "k", "v", force=False
        )


def test_add_value_failure_leaves_the_store_untouched(tmp_path):
    _rules(tmp_path)
    p = _write_store(tmp_path)
    before = p.read_text()
    store = SopsStore(p, run=_add_runner(encrypt_ok=False))
    with pytest.raises(LookupError, match="encrypt"):
        store.add_value("k1", "v", force=False)
    assert p.read_text() == before
    assert [q for q in tmp_path.iterdir() if q.name.startswith(".plane-secrets-")] == []


def test_add_value_refuses_to_replace_with_unencrypted_output(tmp_path):
    # If encryption "succeeds" but the file is still plaintext (wrong rules,
    # a stub, a broken sops), the store must not be replaced.
    _rules(tmp_path)
    p = _write_store(tmp_path)
    before = p.read_text()
    store = SopsStore(p, run=_add_runner(encrypt_writes=False))
    with pytest.raises(LookupError, match="not fully encrypted"):
        store.add_value("k1", "v", force=False)
    assert p.read_text() == before


def test_add_value_refuses_an_unquotable_name(tmp_path):
    _rules(tmp_path)
    store = SopsStore(_write_store(tmp_path), run=_add_runner())
    with pytest.raises(LookupError, match="safely"):
        store.add_value('bad"name', "v", force=False)


def test_add_preview_says_add_or_rotate(tmp_path):
    store = SopsStore(_write_store(tmp_path), run=_add_runner())
    assert "add" in store.add_preview("new_key")[0]
    assert "rotate" in store.add_preview("openrouter_api_key")[0]
