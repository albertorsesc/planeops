"""CLI wiring for `plane drift`, focused on the `--json` output path.

`run_drift` is stubbed so these exercise the CLI branch (flag parsing, what gets
printed, the exit code) without needing a real snapshot on the live host.
"""

import json

from engine.cli import build_parser, main
from engine.core.drift import DriftItem, DriftReport


def _report(alerts=0):
    rep = DriftReport(host="h", ts="2026-07-28T00:00:00")
    rep.alerts = [DriftItem(f"manual/a{i}", "active", "expected present, not observed")
                  for i in range(alerts)]  # fmt: skip
    return rep


def test_drift_json_flag_parses():
    args = build_parser().parse_args(["drift", "--json"])
    assert args.as_json is True
    assert build_parser().parse_args(["drift"]).as_json is False


def test_drift_json_prints_valid_report_and_sets_exit_code(monkeypatch, capsys):
    monkeypatch.setattr("engine.core.drift.run_drift", lambda repo: _report(alerts=2))
    code = main(["drift", "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)  # stdout is pure JSON, nothing else
    assert data["exit_code"] == 2 and data["alert_count"] == 2
    assert len(data["sections"]["alerts"]) == 2
    assert code == 2  # alerts -> non-zero exit, unchanged from the text path


def test_drift_without_json_prints_human_summary_not_json(monkeypatch, capsys):
    monkeypatch.setattr("engine.core.drift.run_drift", lambda repo: _report(alerts=0))
    code = main(["drift"])
    out = capsys.readouterr().out
    assert "alert(s)" in out and "DRIFT.md" in out
    assert not out.lstrip().startswith("{")
    assert code == 0


def _status(alert_count, report=0, uncovered=0):
    return {
        "alert_count": alert_count,
        "ts": "2026-07-29T00:00:00",
        "summary": {"report": report, "uncovered": uncovered},
        "sections": {},
    }


def test_status_prints_summary_and_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(
        "engine.core.status.read_status", lambda repo: _status(2, report=1)
    )
    code = main(["status"])
    out = capsys.readouterr().out
    assert "2 alert(s)" in out and "1 report" in out and "as of 2026-07-29" in out
    assert code == 2


def test_status_short_prints_token_only_when_alerts(monkeypatch, capsys):
    monkeypatch.setattr("engine.core.status.read_status", lambda repo: _status(3))
    assert main(["status", "--short"]) == 2
    assert capsys.readouterr().out == "drift:3\n"

    monkeypatch.setattr("engine.core.status.read_status", lambda repo: _status(0))
    assert main(["status", "--short"]) == 0
    assert capsys.readouterr().out == ""  # clean -> nothing, so the prompt stays clean


def test_status_json_emits_the_stored_report(monkeypatch, capsys):
    monkeypatch.setattr("engine.core.status.read_status", lambda repo: _status(1))
    assert main(["status", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["alert_count"] == 1


def test_status_without_a_report_is_not_an_error(monkeypatch, capsys):
    monkeypatch.setattr("engine.core.status.read_status", lambda repo: None)
    assert main(["status"]) == 0  # unseeded is not a failure
    assert "no drift report" in capsys.readouterr().err


def test_status_short_is_silent_when_no_report(monkeypatch, capsys):
    # A shell prompt on a fresh repo must get nothing, not the stderr hint.
    monkeypatch.setattr("engine.core.status.read_status", lambda repo: None)
    assert main(["status", "--short"]) == 0
    cap = capsys.readouterr()
    assert cap.out == "" and cap.err == ""
