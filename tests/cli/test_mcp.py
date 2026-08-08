"""`plane mcp` wiring: human view, --json contract, unseeded behavior."""

import json
from pathlib import Path

import pytest

from planeops.cli import main
from tests.cli.helpers import _mcp_view


@pytest.fixture
def inst(tmp_path):
    (tmp_path / ".planeops").write_text("")
    return str(tmp_path)


def test_mcp_prints_the_human_view(monkeypatch, capsys, inst):
    monkeypatch.setattr(
        "planeops.adapters.mcp.view.read_mcp_view", lambda repo: _mcp_view()
    )
    assert main(["--repo", inst, "mcp"]) == 0
    out = capsys.readouterr().out
    assert "context7" in out and "ungoverned" in out
    [tolaria_line] = [
        ln for ln in out.splitlines() if "tolaria" in ln and "," not in ln
    ]
    assert "ungoverned" in tolaria_line  # the flag rides the server's own row


def test_mcp_json_emits_the_structured_view(monkeypatch, capsys, inst):
    monkeypatch.setattr(
        "planeops.adapters.mcp.view.read_mcp_view", lambda repo: _mcp_view()
    )
    assert main(["--repo", inst, "mcp", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ungoverned"] == ["tolaria"]


def test_mcp_without_a_snapshot_is_not_an_error(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.adapters.mcp.view.read_mcp_view", lambda repo: None)
    assert main(["--repo", inst, "mcp"]) == 0
    assert "plane observe" in capsys.readouterr().err


def test_mcp_json_unseeded_emits_a_json_error_object(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.adapters.mcp.view.read_mcp_view", lambda repo: None)
    code = main(["--repo", inst, "mcp", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert "error" in data and code == 0


# ---- plane mcp init: the tool wires its own sources ----------------------


def _fake_home_with_clients(tmp_path, monkeypatch):
    # The verb's flow is under test; detection has its own suite, so stub it.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(
        "planeops.adapters.mcp.detect.detect_sources",
        lambda h, **kw: [
            {"label": "claude-code", "path": "~/.claude.json",
             "format": "json", "key": "mcpServers"},
            {"label": "codex", "path": "~/.codex/config.toml",
             "format": "toml", "key": "mcp_servers"},
        ],
    )  # fmt: skip
    return home


def test_mcp_init_previews_and_appends_sources(tmp_path, monkeypatch, capsys):
    _fake_home_with_clients(tmp_path, monkeypatch)
    inst = tmp_path / "inst"
    (inst / "registry").mkdir(parents=True)
    (inst / ".planeops").write_text("")
    (inst / "instance.yaml").write_text("# my precious comment\n")
    assert main(["--repo", str(inst), "mcp", "init", "--yes"]) == 0
    text = (inst / "instance.yaml").read_text()
    assert "# my precious comment" in text  # user content untouched
    assert "label: claude-code" in text and "label: codex" in text
    # and the tool can now read what it wrote
    from planeops.adapters.mcp import load_sources

    labels = [s.label for s in load_sources(inst)]
    assert labels == ["claude-code", "codex"]


def test_mcp_init_skips_sources_already_wired(tmp_path, monkeypatch, capsys):
    _fake_home_with_clients(tmp_path, monkeypatch)
    inst = tmp_path / "inst"
    (inst / "registry").mkdir(parents=True)
    (inst / ".planeops").write_text("")
    (inst / "instance.yaml").write_text(
        "mcp:\n  sources:\n"
        "    - {label: claude-code, path: ~/.claude.json, format: json}\n"
    )
    assert main(["--repo", str(inst), "mcp", "init", "--yes"]) == 0
    from planeops.adapters.mcp import load_sources

    labels = [s.label for s in load_sources(inst)]
    assert labels == ["claude-code", "codex"]  # appended, not duplicated


def test_mcp_init_refuses_without_confirmation(tmp_path, monkeypatch, capsys):
    _fake_home_with_clients(tmp_path, monkeypatch)
    inst = tmp_path / "inst"
    (inst / "registry").mkdir(parents=True)
    (inst / ".planeops").write_text("")
    (inst / "instance.yaml").write_text("x: 1\n")
    monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(EOFError()))
    assert main(["--repo", str(inst), "mcp", "init"]) == 0
    assert "label:" not in (inst / "instance.yaml").read_text()


def test_mcp_init_appends_inside_the_sources_block_not_at_eof(tmp_path, monkeypatch):
    # Real instance files have sections AFTER mcp:; appending at EOF would
    # nest new sources under the wrong block.
    _fake_home_with_clients(tmp_path, monkeypatch)
    inst = tmp_path / "inst"
    (inst / "registry").mkdir(parents=True)
    (inst / ".planeops").write_text("")
    (inst / "instance.yaml").write_text(
        "mcp:\n  sources:\n"
        "    - {label: claude-code, path: ~/.claude.json, format: json}\n"
        "\n"
        "# secrets config lives below\n"
        "secrets:\n  store: sops\n"
    )
    assert main(["--repo", str(inst), "mcp", "init", "--yes"]) == 0
    from planeops.adapters.mcp import load_sources
    from planeops.config import section

    assert [s.label for s in load_sources(inst)] == ["claude-code", "codex"]
    assert section(inst, "secrets") == {"store": "sops"}  # untouched
