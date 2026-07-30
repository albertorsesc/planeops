"""`plane import --write`: land proposed entries into registry/imported.yaml.

Turns onboarding from hand-authoring YAML into pruning a generated list: `observe`
then `import observed --write` seeds the registry from the machine itself.
"""

import json

import yaml

from engine.cli import main
from engine.core.registry import load_registry
from engine.importers import write_proposal


def _entries(*ids):
    return [
        {
            "id": i,
            "adapter": i.split("/")[0],
            "domain": "package",
            "lifecycle": "active",
            "tolerance": "report",
            "intent": "imported, verify",
        }
        for i in ids
    ]


def test_write_proposal_creates_then_merges_without_dupes(tmp_path):
    (tmp_path / "registry").mkdir()
    p, total = write_proposal(_entries("pkg-brew/a", "pkg-brew/b"), tmp_path)
    assert p == tmp_path / "registry" / "imported.yaml"
    ids = [e["id"] for e in yaml.safe_load(p.read_text())["entries"]]
    assert ids == ["pkg-brew/a", "pkg-brew/b"] and total == 2
    # a second write merges: keeps existing, adds new, de-dups the repeat
    _, total2 = write_proposal(_entries("pkg-brew/b", "pkg-brew/c"), tmp_path)
    ids = [e["id"] for e in yaml.safe_load(p.read_text())["entries"]]
    assert ids == ["pkg-brew/a", "pkg-brew/b", "pkg-brew/c"] and total2 == 3


def _snapshot(observed, host="testhost"):
    return json.dumps({"host": host, "observed": observed})


def test_cli_import_write_seeds_the_registry(tmp_path, capsys):
    reg = tmp_path / "registry"
    reg.mkdir()
    (tmp_path / ".planeops").write_text("")
    snap = tmp_path / "snap.json"
    snap.write_text(
        _snapshot(
            [
                {"adapter": "ollama", "native_id": "m1", "facts": {}},
                {"adapter": "mcp", "native_id": "context7", "facts": {}},
            ]
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


def test_cli_import_write_without_yes_and_no_tty_does_not_write(tmp_path, capsys):
    # Non-interactive without --yes must not silently mutate the registry.
    reg = tmp_path / "registry"
    reg.mkdir()
    (tmp_path / ".planeops").write_text("")
    snap = tmp_path / "snap.json"
    snap.write_text(_snapshot([{"adapter": "ollama", "native_id": "m1", "facts": {}}]))
    code = main(["--repo", str(tmp_path), "import", "observed", str(snap), "--write"])
    assert code == 0
    assert not (reg / "imported.yaml").exists()  # nothing written without confirmation
