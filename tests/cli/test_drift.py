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


def _grouped_report():
    """Two adapters, one with rows that agree on their message and one row
    that disagrees, so both rendering paths appear in a single report."""
    from planeops.core.report import DriftItem, DriftReport

    rep = DriftReport(host="h", ts="2026-07-28T00:00:00")
    rep.ungoverned = [
        DriftItem("manual/a0", "active", "observed but not in the registry"),
        DriftItem("manual/a1", "active", "observed but not in the registry"),
        DriftItem("launchd/svc", "active", "observed but not in the registry"),
    ]
    rep.alerts = [
        DriftItem("manual/b0", "retired", "listed retired but still present"),
        DriftItem("manual/b1", "retired", "listed retired but still present"),
        DriftItem("secrets/key", "active", "required secret is not configured"),
    ]
    return rep


def test_a_shared_message_is_stated_once_on_the_group(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.drift.run_drift", lambda repo: _grouped_report())
    main(["--repo", inst, "drift"])
    out = capsys.readouterr().out
    assert "manual · listed retired but still present" in out
    assert out.count("listed retired but still present") == 1


def test_the_adapter_prefix_is_hoisted_off_the_rows(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.drift.run_drift", lambda repo: _grouped_report())
    main(["--repo", inst, "drift"])
    out = capsys.readouterr().out
    assert "manual/b0" not in out and "b0" in out  # bare under its group
    assert "launchd/svc" not in out and "svc" in out


def test_a_row_that_disagrees_keeps_its_own_message(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.drift.run_drift", lambda repo: _grouped_report())
    main(["--repo", inst, "drift"])
    assert "required secret is not configured" in capsys.readouterr().out


def test_every_adapter_present_gets_its_own_group(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.drift.run_drift", lambda repo: _grouped_report())
    out = (main(["--repo", inst, "drift"]), capsys.readouterr().out)[1]
    for adapter in ("manual", "launchd", "secrets"):
        assert adapter in out


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
