import yaml

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
