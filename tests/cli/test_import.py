"""`plane import` wiring: the observed default path, --write confirmation, and
the path requirement for other kinds. Importer logic lives in tests/importers/."""

import json

from planeops.cli import main
from planeops.core.registry import load_registry


def _snapshot(observed, host="h"):
    return json.dumps({"host": host, "observed": observed})


def test_import_observed_defaults_to_the_host_snapshot(monkeypatch, capsys, tmp_path):
    # The CLI computes this path everywhere else; making the user retype it was
    # pure friction. `plane import observed` alone now reads it.
    class _Plat:
        name = "fake"

        def hostname(self):
            return "h"

        def home(self):
            return tmp_path

    monkeypatch.setattr("planeops.platform.current_platform", lambda: _Plat())
    inst = tmp_path / "inst"
    (inst / "registry").mkdir(parents=True)
    (inst / ".planeops").write_text("")
    snapdir = inst / "observed" / "h"
    snapdir.mkdir(parents=True)
    (snapdir / "snapshot.json").write_text(
        _snapshot([{"adapter": "manual", "native_id": "x", "facts": {}}])
    )
    assert main(["--repo", str(inst), "import", "observed"]) == 0
    out = capsys.readouterr().out
    assert "manual/x" in out  # proposal printed from the defaulted snapshot


def test_import_other_kinds_still_require_a_path(capsys, tmp_path):
    (tmp_path / ".planeops").write_text("")
    assert main(["--repo", str(tmp_path), "import", "envfile"]) == 1
    assert "path" in capsys.readouterr().err


def test_import_write_seeds_the_registry(tmp_path, capsys):
    reg = tmp_path / "registry"
    reg.mkdir()
    (tmp_path / ".planeops").write_text("")
    snap = tmp_path / "snap.json"
    snap.write_text(
        _snapshot(
            [
                {"adapter": "ollama", "native_id": "m1", "facts": {}},
                {"adapter": "mcp", "native_id": "context7", "facts": {}},
            ],
            host="testhost",
        )
    )
    code = main(
        ["--repo", str(tmp_path), "import", "observed", str(snap), "--write", "--yes"]
    )
    assert code == 0
    # the proposed entries now load as real registry entries
    ids = {e.id for e in load_registry(reg).entries}
    assert ids == {"ollama/m1", "mcp/context7"}
    # re-running writes nothing new (they are declared now -> prune-not-duplicate)
    capsys.readouterr()
    code = main(
        ["--repo", str(tmp_path), "import", "observed", str(snap), "--write", "--yes"]
    )
    assert code == 0
    assert "nothing new" in capsys.readouterr().out.lower()


def test_import_write_without_yes_and_no_tty_does_not_write(tmp_path):
    # Non-interactive without --yes must not silently mutate the registry.
    reg = tmp_path / "registry"
    reg.mkdir()
    (tmp_path / ".planeops").write_text("")
    snap = tmp_path / "snap.json"
    snap.write_text(_snapshot([{"adapter": "ollama", "native_id": "m1", "facts": {}}]))
    code = main(["--repo", str(tmp_path), "import", "observed", str(snap), "--write"])
    assert code == 0
    assert not (reg / "imported.yaml").exists()  # nothing written without confirmation
