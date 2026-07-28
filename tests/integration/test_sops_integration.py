"""Integration: the secrets path against the REAL sops + age binaries.

Unit tests fake the runner; these prove the actual `sops -d` round-trip and that a
real decrypted value still lands only in the target, redacted everywhere else.
Skipped when the binaries are absent (so `pytest` stays green without them); CI
installs them so this runs on Linux on every PR.
"""

import shutil
import subprocess
from datetime import datetime

import pytest

from engine.adapters.secrets import SecretsAdapter
from engine.core.contracts import Ctx
from engine.core.schema import entry_from_dict
from engine.secrets import materialization_handle
from engine.secrets.sops import SopsBackend

pytestmark = pytest.mark.skipif(
    shutil.which("sops") is None or shutil.which("age") is None,
    reason="requires the real sops and age binaries",
)

VALUE = "sk-integration-REAL-value-0xABCDEF12345"


def _encrypted_store(tmp_path, monkeypatch):
    key = tmp_path / "age.key"
    subprocess.run(["age-keygen", "-o", str(key)], check=True, capture_output=True)
    recipient = subprocess.run(
        ["age-keygen", "-y", str(key)], check=True, capture_output=True, text=True
    ).stdout.strip()
    monkeypatch.setenv("SOPS_AGE_KEY_FILE", str(key))  # inherited by the real `sops -d`
    plain = tmp_path / "plain.yaml"
    plain.write_text(f"api-key: {VALUE}\n")
    store = tmp_path / "secrets.sops.yaml"
    with store.open("w") as fh:
        subprocess.run(
            ["sops", "--encrypt", "--age", recipient, "--input-type", "yaml",
             "--output-type", "yaml", str(plain)],
            check=True, stdout=fh,
        )  # fmt: skip
    plain.unlink()
    return store


def test_sops_backend_round_trips_a_real_store(tmp_path, monkeypatch):
    store = _encrypted_store(tmp_path, monkeypatch)
    assert VALUE not in store.read_text()  # ciphertext at rest
    backend = SopsBackend(store)
    assert backend.exists("api-key")
    assert not backend.exists("nope")
    assert backend.get("api-key") == VALUE  # real `sops -d --extract`


def test_materialize_from_a_real_store_redacts_everywhere(tmp_path, monkeypatch):
    store = _encrypted_store(tmp_path, monkeypatch)
    target = tmp_path / "env"
    consumer = entry_from_dict(
        {
            "id": "manual/consumer",
            "adapter": "manual",
            "domain": "host",
            "lifecycle": "active",
            "intent": "i",
            "secrets": [
                {
                    "ref": "secret://sops/api-key",
                    "injected_as": f"file:{target}#API_KEY",
                }
            ],
        }
    )
    secret = entry_from_dict(
        {
            "id": "secrets/api-key",
            "adapter": "secrets",
            "domain": "secret",
            "lifecycle": "active",
            "intent": "i",
        }
    )
    entries = (secret, consumer)
    ctx = Ctx(platform=None, host="h", now=datetime(2026, 7, 28),
              entries=entries, repo_root=tmp_path)  # fmt: skip
    [change] = SecretsAdapter().plan(secret, None, ctx)
    assert VALUE not in change.diff

    handle = materialization_handle(SopsBackend(store))
    exec_ctx = Ctx(platform=None, host="h", now=datetime(2026, 7, 28),
                   entries=entries, repo_root=tmp_path, secrets=handle)  # fmt: skip
    res = SecretsAdapter().execute(change, exec_ctx)

    assert res.ok and VALUE not in res.detail
    assert target.read_text() == f"API_KEY={VALUE}\n"  # decrypted value only here
    assert target.stat().st_mode & 0o777 == 0o600
