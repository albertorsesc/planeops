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
