"""`plane mcp` wiring: human view, --json contract, unseeded behavior."""

import json

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
    assert "context7" in out and "(ungoverned)" in out


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
