"""`plane drift` wiring: the --json contract, the human summary, exit codes."""

import json

import pytest

from planeops.cli import build_parser, main
from tests.cli.helpers import _report


@pytest.fixture
def inst(tmp_path):
    (tmp_path / ".planeops").write_text("")
    return str(tmp_path)


def test_drift_json_flag_parses():
    args = build_parser().parse_args(["drift", "--json"])
    assert args.as_json is True
    assert build_parser().parse_args(["drift"]).as_json is False


def test_drift_json_prints_valid_report_and_sets_exit_code(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.drift.run_drift", lambda repo: _report(alerts=2))
    code = main(["--repo", inst, "drift", "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)  # stdout is pure JSON, nothing else
    assert data["exit_code"] == 2 and data["alert_count"] == 2
    assert len(data["sections"]["alerts"]) == 2
    assert code == 2  # alerts -> non-zero exit, unchanged from the text path


def test_drift_without_json_prints_human_summary_not_json(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.drift.run_drift", lambda repo: _report(alerts=0))
    code = main(["--repo", inst, "drift"])
    out = capsys.readouterr().out
    assert "no drift" in out
    assert not out.lstrip().startswith("{")
    assert code == 0


def test_drift_json_unseeded_emits_a_json_error_object(monkeypatch, capsys, inst):
    # The --json contract holds for every verb: stdout parses as JSON even when
    # the snapshot is missing; the exit code still says operator error.
    def _raise(repo):
        raise FileNotFoundError("no readable snapshot at x; run `plane observe` first")

    monkeypatch.setattr("planeops.core.drift.run_drift", _raise)
    code = main(["--repo", inst, "drift", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert "error" in data and "plane observe" in data["error"]
    assert code == 1
