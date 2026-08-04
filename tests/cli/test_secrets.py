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


# ---- `plane secrets add`: value entry that never touches argv ----


class _AddRecorder:
    """Fake sops for the add flow: decrypt returns an empty mapping, encrypt
    rewrites the target with ENC[...] values plus the metadata block."""

    def __init__(self, decrypt_out="{}\n"):
        self.calls: list[list[str]] = []
        self._decrypt_out = decrypt_out

    def __call__(self, cmd, timeout=None):
        self.calls.append(list(cmd))
        if cmd[:2] == ["sops", "-d"]:
            return RunResult(0, self._decrypt_out, "")
        if cmd[0] == "sops" and "-e" in cmd:
            from planeops.providers import yaml

            target = Path(cmd[-1])
            data = yaml.load(target.read_text()) or {}
            enc = {k: f"ENC[AES256_GCM,data:{k}]" for k in data}
            enc["sops"] = {"version": "3"}
            target.write_text(yaml.dump(enc))
            return RunResult(0)
        return RunResult(127, "", f"{cmd[0]}: not found")


def _bootstrapped(tmp_path):
    inst = _inst(tmp_path)
    (inst / ".sops.yaml").write_text(
        "creation_rules:\n  - path_regex: secrets\\.sops\\.yaml$\n    age: age1x\n"
    )
    (inst / "secrets.sops.yaml").write_text("{}\nsops:\n  version: '3'\n")
    return inst


class _Pipe:
    """Non-tty stdin carrying one piped value."""

    def __init__(self, line):
        self._line = line

    def isatty(self):
        return False

    def readline(self):
        return self._line


def test_secrets_add_piped_value_stays_off_argv(tmp_path, monkeypatch):
    inst = _bootstrapped(tmp_path)
    rec = _AddRecorder()
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", rec)
    monkeypatch.setattr("sys.stdin", _Pipe("hunter2\n"))
    assert main(["--repo", str(inst), "secrets", "add", "tg-token", "--yes"]) == 0
    text = (inst / "secrets.sops.yaml").read_text()
    assert "tg-token" in text and "hunter2" not in text
    for cmd in rec.calls:
        assert all("hunter2" not in arg for arg in cmd), cmd


def test_secrets_add_piped_without_yes_is_refused(tmp_path, monkeypatch):
    inst = _bootstrapped(tmp_path)
    before = (inst / "secrets.sops.yaml").read_text()
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", _AddRecorder())
    monkeypatch.setattr("sys.stdin", _Pipe("v\n"))
    assert main(["--repo", str(inst), "secrets", "add", "k"]) == 1
    assert (inst / "secrets.sops.yaml").read_text() == before


class _Tty(_Pipe):
    def isatty(self):
        return True


def test_secrets_add_interactive_requires_matching_blind_entries(
    tmp_path, monkeypatch, capsys
):
    inst = _bootstrapped(tmp_path)
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", _AddRecorder())
    monkeypatch.setattr("sys.stdin", _Tty(""))
    prompts = iter(["value-1", "value-2"])
    monkeypatch.setattr("getpass.getpass", lambda *a: next(prompts))
    assert main(["--repo", str(inst), "secrets", "add", "k"]) == 1
    assert "did not match" in capsys.readouterr().err
    prompts = iter(["same", "same"])
    monkeypatch.setattr("getpass.getpass", lambda *a: next(prompts))
    assert main(["--repo", str(inst), "secrets", "add", "k"]) == 0
    assert "k" in (inst / "secrets.sops.yaml").read_text()


def test_secrets_add_empty_value_is_refused(tmp_path, monkeypatch):
    inst = _bootstrapped(tmp_path)
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", _AddRecorder())
    monkeypatch.setattr("sys.stdin", _Pipe("\n"))
    assert main(["--repo", str(inst), "secrets", "add", "k", "--yes"]) == 1


def test_secrets_add_rejects_a_name_outside_the_ref_grammar(tmp_path, monkeypatch):
    inst = _bootstrapped(tmp_path)
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", _AddRecorder())
    monkeypatch.setattr("sys.stdin", _Pipe("v\n"))
    assert main(["--repo", str(inst), "secrets", "add", "bad name", "--yes"]) == 1


def test_secrets_add_existing_name_needs_force(tmp_path, monkeypatch, capsys):
    inst = _bootstrapped(tmp_path)
    (inst / "secrets.sops.yaml").write_text(
        "k: ENC[AES256_GCM,data:x]\nsops:\n  version: '3'\n"
    )
    rec = _AddRecorder(decrypt_out="k: old\n")
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", rec)
    monkeypatch.setattr("sys.stdin", _Pipe("new\n"))
    assert main(["--repo", str(inst), "secrets", "add", "k", "--yes"]) == 1
    assert "--force" in capsys.readouterr().err
    assert main(["--repo", str(inst), "secrets", "add", "k", "--yes", "--force"]) == 0


# ---- first use: add offers the store's own bootstrap inline ----


class _FullRecorder:
    """Fake age-keygen + sops for the bootstrap-then-add flow. Encryption is a
    uniform transform (ENC-wrap every key, append metadata), which serves both
    the bootstrap's empty store and add's temp file."""

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
        if cmd[:2] == ["sops", "-d"]:
            return RunResult(0, "{}\n", "")
        if cmd[0] == "sops" and "-e" in cmd:
            from planeops.providers import yaml

            target = Path(cmd[-1])
            data = yaml.load(target.read_text()) or {}
            enc = {k: f"ENC[AES256_GCM,data:{k}]" for k in data}
            enc["sops"] = {"version": "3"}
            target.write_text(yaml.dump(enc))
            return RunResult(0)
        return RunResult(127, "", f"{cmd[0]}: not found")


def test_secrets_add_bootstraps_an_absent_store_inline(tmp_path, monkeypatch, capsys):
    inst = _inst(tmp_path)  # no store, no rules
    rec = _FullRecorder()
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", rec)
    monkeypatch.setattr("sys.stdin", _Pipe("hunter2\n"))
    assert main(["--repo", str(inst), "secrets", "add", "tg-token", "--yes",
                 "--age-key", str(tmp_path / "k.txt")]) == 0  # fmt: skip
    out = capsys.readouterr().out
    assert "add will first initialize it" in out
    assert (inst / ".sops.yaml").exists()
    text = (inst / "secrets.sops.yaml").read_text()
    assert "tg-token" in text and "hunter2" not in text
    for cmd in rec.calls:
        assert all("hunter2" not in arg for arg in cmd), cmd


def test_secrets_add_bootstrap_declined_writes_nothing(tmp_path, monkeypatch):
    inst = _inst(tmp_path)
    rec = _FullRecorder()
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", rec)
    monkeypatch.setattr("sys.stdin", _Tty(""))
    monkeypatch.setattr("builtins.input", lambda *a: "n")
    called = []
    monkeypatch.setattr("getpass.getpass", lambda *a: called.append(1) or "v")
    assert main(["--repo", str(inst), "secrets", "add", "k"]) == 0
    assert not (inst / "secrets.sops.yaml").exists()
    assert not (inst / ".sops.yaml").exists()
    assert called == []  # declined before any value prompt
    assert rec.calls == []


def test_secrets_add_interactive_confirms_bootstrap_then_prompts(tmp_path, monkeypatch):
    inst = _inst(tmp_path)
    rec = _FullRecorder()
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", rec)
    monkeypatch.setattr("sys.stdin", _Tty(""))
    monkeypatch.setattr("builtins.input", lambda *a: "y")
    prompts = iter(["same", "same"])
    monkeypatch.setattr("getpass.getpass", lambda *a: next(prompts))
    assert main(["--repo", str(inst), "secrets", "add", "k",
                 "--age-key", str(tmp_path / "k.txt")]) == 0  # fmt: skip
    assert "k" in (inst / "secrets.sops.yaml").read_text()


def test_secrets_add_piped_without_yes_refuses_before_bootstrap(tmp_path, monkeypatch):
    inst = _inst(tmp_path)
    rec = _FullRecorder()
    monkeypatch.setattr("planeops.secrets.stores.sops.default_run", rec)
    monkeypatch.setattr("sys.stdin", _Pipe("v\n"))
    assert main(["--repo", str(inst), "secrets", "add", "k"]) == 1
    assert rec.calls == []  # refused before creating anything
    assert not (inst / "secrets.sops.yaml").exists()
