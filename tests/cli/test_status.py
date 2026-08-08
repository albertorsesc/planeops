"""`plane status` wiring: summary/short/json modes, unseeded and degraded reports."""

import json

import pytest

from planeops.cli import main
from tests.cli.helpers import _status


@pytest.fixture
def inst(tmp_path):
    # A marked instance, so resolution is hermetic (never the developer's or
    # CI's real config/cwd) and the marker note stays out of stderr.
    (tmp_path / ".planeops").write_text("")
    return str(tmp_path)


def test_status_prints_summary_and_exit_code(monkeypatch, capsys, inst):
    monkeypatch.setattr(
        "planeops.core.status.read_status", lambda repo: _status(2, report=1)
    )
    code = main(["--repo", inst, "status"])
    out = capsys.readouterr().out
    assert "2 alert(s)" in out
    assert code == 2


def test_status_short_prints_token_only_when_alerts(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.status.read_status", lambda repo: _status(3))
    assert main(["--repo", inst, "status", "--short"]) == 2
    assert capsys.readouterr().out.strip() == "drift:3"
    monkeypatch.setattr("planeops.core.status.read_status", lambda repo: _status(0))
    assert main(["--repo", inst, "status", "--short"]) == 0
    assert capsys.readouterr().out == ""  # clean: silent, prompt-friendly


def test_status_json_emits_the_stored_report(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.status.read_status", lambda repo: _status(1))
    assert main(["--repo", inst, "status", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["alert_count"] == 1


def test_status_without_a_report_is_not_an_error(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.status.read_status", lambda repo: None)
    assert main(["--repo", inst, "status"]) == 0
    assert "no drift report yet" in capsys.readouterr().err


def test_status_short_is_silent_when_no_report(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.status.read_status", lambda repo: None)
    assert main(["--repo", inst, "status", "--short"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""  # a prompt never sees noise


def test_status_json_unseeded_emits_a_json_error_object(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.status.read_status", lambda repo: None)
    code = main(["--repo", inst, "status", "--json"])
    data = json.loads(capsys.readouterr().out)  # stdout parses even when unseeded
    assert "error" in data and code == 0


def test_status_tolerates_a_hand_edited_partial_report(monkeypatch, capsys, inst):
    # A user (or an older engine) may leave DRIFT.json with missing keys; the
    # prompt path must degrade, never traceback.
    monkeypatch.setattr("planeops.core.status.read_status", lambda repo: {"ts": "t"})
    code = main(["--repo", inst, "status"])
    out = capsys.readouterr().out
    assert "clean" in out and code == 0


def test_full_status_names_the_instance(monkeypatch, capsys, tmp_path):
    (tmp_path / ".planeops").write_text("")
    monkeypatch.setattr(
        "planeops.core.status.read_status",
        lambda repo: {"alert_count": 0, "ts": "t", "summary": {}},
    )
    assert main(["--repo", str(tmp_path), "status"]) == 0
    out = capsys.readouterr().out
    assert "instance" in out and str(tmp_path) in out


def test_short_status_stays_bare(monkeypatch, capsys, tmp_path):
    (tmp_path / ".planeops").write_text("")
    monkeypatch.setattr(
        "planeops.core.status.read_status",
        lambda repo: {"alert_count": 0, "ts": "t", "summary": {}},
    )
    assert main(["--repo", str(tmp_path), "status", "--short"]) == 0
    assert capsys.readouterr().out == ""  # nothing but the token contract
