"""`plane secrets init`: the tool bootstraps its own store, cwd-proof."""

from pathlib import Path

from planeops._run import RunResult
from planeops.cli import main


class _Recorder:
    """Fake runner standing in for sops/age: records argv, writes plausible
    outputs so the flow completes."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, cmd, timeout=None):
        self.calls.append(list(cmd))
        if cmd[0] == "age-keygen":
            Path(cmd[2]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[2]).write_text(
                "# created: t\n# public key: age1testkey\nAGE-SECRET-KEY-1X\n"
            )
            return RunResult(0, "Public key: age1testkey\n")
        if cmd[0] == "sops":
            # `sops -e -i <file>`: stand in for encryption in place.
            target = Path(cmd[-1])
            target.write_text("canary: ENC[AES256_GCM,data:x]\nsops:\n  version: '3'\n")
            return RunResult(0)
        return RunResult(127, "", f"{cmd[0]}: not found")


def _inst(tmp_path):
    inst = tmp_path / "inst"
    (inst / "registry").mkdir(parents=True)
    (inst / ".planeops").write_text("")
    return inst


def test_secrets_init_bootstraps_cwd_proof(tmp_path, monkeypatch):
    # The whole point: no command may depend on the working directory. The
    # provider must pass --config explicitly to every sops invocation.
    inst = _inst(tmp_path)
    key = tmp_path / "keys" / "keys.txt"
    rec = _Recorder()
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", rec)
    monkeypatch.chdir(tmp_path)  # deliberately NOT the instance
    assert main(["--repo", str(inst), "secrets", "init", "--yes",
                 "--age-key", str(key)]) == 0  # fmt: skip
    assert (inst / ".sops.yaml").exists()
    assert "age1testkey" in (inst / ".sops.yaml").read_text()
    assert (inst / "secrets.sops.yaml").exists()
    sops_calls = [c for c in rec.calls if c[0] == "sops"]
    assert sops_calls, "sops was never invoked"
    for call in sops_calls:
        assert "--config" in call, f"cwd-dependent sops call: {call}"


def test_secrets_init_reuses_an_existing_identity(tmp_path, monkeypatch):
    inst = _inst(tmp_path)
    key = tmp_path / "keys" / "keys.txt"
    key.parent.mkdir(parents=True)
    key.write_text("# public key: age1existing\nAGE-SECRET-KEY-1Y\n")
    rec = _Recorder()
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", rec)
    assert main(["--repo", str(inst), "secrets", "init", "--yes",
                 "--age-key", str(key)]) == 0  # fmt: skip
    assert not any(c[0] == "age-keygen" for c in rec.calls)  # no new key minted
    assert "age1existing" in (inst / ".sops.yaml").read_text()


def test_secrets_init_previews_and_refuses_without_confirmation(tmp_path, monkeypatch):
    inst = _inst(tmp_path)
    rec = _Recorder()
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", rec)
    monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(EOFError()))
    assert main(["--repo", str(inst), "secrets", "init",
                 "--age-key", str(tmp_path / "k.txt")]) == 0  # fmt: skip
    assert not (inst / ".sops.yaml").exists()  # nothing written
    assert not (inst / "secrets.sops.yaml").exists()


def test_secrets_init_never_overwrites_an_existing_store(tmp_path, monkeypatch):
    inst = _inst(tmp_path)
    (inst / "secrets.sops.yaml").write_text("k: ENC[x]\nsops: {}\n")
    rec = _Recorder()
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", rec)
    assert main(["--repo", str(inst), "secrets", "init", "--yes",
                 "--age-key", str(tmp_path / "k.txt")]) == 1  # fmt: skip
    assert (inst / "secrets.sops.yaml").read_text() == "k: ENC[x]\nsops: {}\n"
