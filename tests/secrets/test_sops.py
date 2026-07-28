import pytest
import yaml

from engine._run import RunResult
from engine.secrets.sops import SopsBackend

# A sops file: keys plaintext, values encrypted, plus the `sops` metadata block.
STORE = {
    "openrouter_api_key": "ENC[AES256_GCM,data:abc,type:str]",
    "anthropic_api_key": "ENC[AES256_GCM,data:def,type:str]",
    "sops": {"age": [{"recipient": "age1example"}], "version": "3.8.1"},
}


def _write_store(tmp_path):
    p = tmp_path / "secrets.sops.yaml"
    p.write_text(yaml.safe_dump(STORE))
    return p


def test_exists_reads_keys_without_decrypting(tmp_path):
    b = SopsBackend(_write_store(tmp_path))
    assert b.exists("openrouter_api_key")
    assert b.exists("anthropic_api_key")
    assert not b.exists("nonexistent_key")


def test_sops_metadata_block_is_not_a_secret(tmp_path):
    assert not SopsBackend(_write_store(tmp_path)).exists("sops")


def test_missing_store_is_empty(tmp_path):
    b = SopsBackend(tmp_path / "nope.yaml")
    assert not b.exists("anything")
    assert b.meta("anything") is None


def test_malformed_store_degrades_not_crashes(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("{ not: valid: yaml")
    assert not SopsBackend(bad).exists("x")


def test_meta_present_for_configured_secret(tmp_path):
    assert SopsBackend(_write_store(tmp_path)).meta("openrouter_api_key") == {
        "configured": True
    }


def test_get_decrypts_via_sops(tmp_path):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return RunResult(0, "sk-secret-value\n", "")

    b = SopsBackend(_write_store(tmp_path), run=fake_run)
    assert b.get("openrouter_api_key") == "sk-secret-value"  # trailing newline trimmed
    assert calls == [
        ["sops", "-d", "--extract", '["openrouter_api_key"]', str(b._store)]
    ]


def test_get_refuses_an_absent_key_without_shelling_out(tmp_path):
    called = False

    def fake_run(cmd):
        nonlocal called
        called = True
        return RunResult(0, "", "")

    b = SopsBackend(_write_store(tmp_path), run=fake_run)
    with pytest.raises(KeyError):
        b.get("nonexistent_key")
    assert called is False


def test_get_raises_when_sops_fails(tmp_path):
    b = SopsBackend(_write_store(tmp_path), run=lambda cmd: RunResult(1, "", "no key"))
    with pytest.raises(RuntimeError):
        b.get("openrouter_api_key")
