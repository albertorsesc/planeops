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


def _mcp_view():
    return {
        "host": "h",
        "ts": "2026-07-29T00:00:00",
        "servers": [
            {
                "name": "context7",
                "id": "mcp/context7",
                "clients": ["claude-code"],
                "governed": True,
            },
            {
                "name": "tolaria",
                "id": "mcp/tolaria",
                "clients": ["cursor"],
                "governed": False,
            },
        ],
        "single_client": ["context7", "tolaria"],
        "ungoverned": ["tolaria"],
        "name_drift": [],
    }


def test_mcp_prints_the_human_view(monkeypatch, capsys):
    monkeypatch.setattr("engine.core.mcp_view.read_mcp_view", lambda repo: _mcp_view())
    assert main(["mcp"]) == 0
    out = capsys.readouterr().out
    assert "context7" in out and "tolaria" in out
    assert not out.lstrip().startswith("{")  # human view, not JSON


def test_mcp_json_emits_the_structured_view(monkeypatch, capsys):
    monkeypatch.setattr("engine.core.mcp_view.read_mcp_view", lambda repo: _mcp_view())
    assert main(["mcp", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ungoverned"] == ["tolaria"]


def test_mcp_without_a_snapshot_is_not_an_error(monkeypatch, capsys):
    monkeypatch.setattr("engine.core.mcp_view.read_mcp_view", lambda repo: None)
    assert main(["mcp"]) == 0  # unseeded is not a failure
    assert "no snapshot" in capsys.readouterr().err


def test_reconcile_observes_then_drifts_and_returns_drift_exit_code(
    monkeypatch, capsys
):
    calls = []
    monkeypatch.setattr(
        "engine.core.observe.run_observe",
        lambda repo, **k: calls.append("observe") or {"observed": [1, 2], "host": "h"},
    )
    monkeypatch.setattr(
        "engine.core.drift.run_drift",
        lambda repo: calls.append("drift") or _report(alerts=3),
    )
    code = main(["reconcile"])
    assert calls == ["observe", "drift"]  # observe first, then drift on the fresh snap
    out = capsys.readouterr().out
    assert "observed 2" in out and "3 alert(s)" in out
    assert code == 2  # alerts -> non-zero, same as `drift`


def test_reconcile_clean_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(
        "engine.core.observe.run_observe",
        lambda repo, **k: {"observed": [], "host": "h"},
    )
    monkeypatch.setattr("engine.core.drift.run_drift", lambda repo: _report(alerts=0))
    assert main(["reconcile"]) == 0


# ---- apply tells the truth (audit wave 1-B) ----


def test_apply_unknown_id_is_an_error(monkeypatch, capsys, tmp_path):
    def _raise(repo, *, only_id=None, only_phase=None):
        raise LookupError("no registry entry with id 'launchd/typo'")

    monkeypatch.setattr("engine.core.apply.run_apply", _raise)
    code = main(["--repo", str(tmp_path), "apply", "--id", "launchd/typo"])
    assert code == 1
    assert "launchd/typo" in capsys.readouterr().err


def test_apply_no_changes_reports_remaining_drift(monkeypatch, capsys, tmp_path):
    # "no changes to apply; machine matches desired state" lied whenever drift had
    # alerts that no adapter could plan away (service file absent, uncovered,
    # owner: human). The message must be neutral and surface the standing alerts.
    monkeypatch.setattr(
        "engine.core.apply.run_apply", lambda repo, *, only_id=None, only_phase=None: []
    )
    monkeypatch.setattr("engine.core.status.read_status", lambda repo: _status(2))
    code = main(["--repo", str(tmp_path), "apply"])
    out = capsys.readouterr().out
    assert "machine matches desired state" not in out
    assert "no changes planned" in out
    assert "2 alert(s)" in out
    assert code == 0


def test_apply_refreshes_drift_after_execute(monkeypatch, capsys, tmp_path):
    # After a converge, DRIFT.json used to stay stale (only observe re-ran), so the
    # shell prompt kept the pre-apply alert count for up to a scheduler interval.
    from engine.core.apply import Applied
    from engine.core.contracts import Change, Result

    calls = []
    done = Applied(
        Change("x/y", "configure", "d", {}), True, Result(ok=True, detail="ok")
    )
    monkeypatch.setattr(
        "engine.core.apply.run_apply",
        lambda repo, *, only_id=None, only_phase=None: [done],
    )
    monkeypatch.setattr(
        "engine.core.observe.run_observe",
        lambda repo: (
            calls.append("observe") or {"observed": [], "uncovered": [], "host": "h"}
        ),
    )
    monkeypatch.setattr(
        "engine.core.drift.run_drift", lambda repo: calls.append("drift") or _report()
    )
    code = main(["--repo", str(tmp_path), "apply"])
    assert calls == ["observe", "drift"]  # panes recomputed, prompt is fresh
    assert code == 0


# ---- schedule observes, so the hinted `plane apply` works first-use ----


class _SchedPlat:
    name = "fake"

    def __init__(self, home):
        self._home = home

    def home(self):
        return self._home

    def hostname(self):
        return "h"


def test_schedule_observes_after_writing(monkeypatch, tmp_path):
    # `plane apply` plans from the snapshot; without a refresh the just-written
    # timer file is invisible and apply says "no changes planned" on first use.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("engine.platform.current_platform", lambda: _SchedPlat(home))
    inst = tmp_path / "inst"
    (inst / "registry").mkdir(parents=True)
    (inst / ".planeops").write_text("")
    seen = []
    monkeypatch.setattr(
        "engine.core.observe.run_observe",
        lambda repo: (
            seen.append(repo) or {"observed": [], "uncovered": [], "host": "h"}
        ),
    )
    assert main(["--repo", str(inst), "schedule", "--every", "6h", "--yes"]) == 0
    assert seen == [inst.resolve()]


# ---- failed adapter scans are visible at the CLI (audit wave 1-C) ----


def test_observe_warns_about_failed_adapter_scans(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        "engine.core.observe.run_observe",
        lambda repo, attest=False: {
            "observed": [],
            "uncovered": [],
            "host": "h",
            "failed": [{"adapter": "pkg-brew", "error": "boom"}],
        },
    )
    assert main(["--repo", str(tmp_path), "observe"]) == 0
    err = capsys.readouterr().err
    assert "pkg-brew" in err and "failed" in err


# ---- uniform verb error handling (audit wave 3-H) ----


def _schema_boom(*a, **k):
    from engine.core.schema import SchemaError

    raise SchemaError("entry 'x': lifecycle=nope is not one of: active, ...")


def test_observe_schema_error_is_clean_exit_1(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("engine.core.observe.run_observe", _schema_boom)
    assert main(["--repo", str(tmp_path), "observe"]) == 1
    assert "lifecycle=nope" in capsys.readouterr().err  # message, not a traceback


def test_drift_schema_error_is_clean_exit_1(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("engine.core.drift.run_drift", _schema_boom)
    assert main(["--repo", str(tmp_path), "drift"]) == 1
    assert "lifecycle=nope" in capsys.readouterr().err


def test_apply_schema_error_is_clean_exit_1(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("engine.core.apply.run_apply", _schema_boom)
    assert main(["--repo", str(tmp_path), "apply"]) == 1
    assert "lifecycle=nope" in capsys.readouterr().err


# ---- --json is a machine contract: stdout is always JSON ----


def test_status_json_unseeded_emits_a_json_error_object(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("engine.core.status.read_status", lambda repo: None)
    code = main(["--repo", str(tmp_path), "status", "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)  # stdout parses as JSON even when unseeded
    assert "error" in data and code == 0


def test_mcp_json_unseeded_emits_a_json_error_object(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("engine.core.mcp_view.read_mcp_view", lambda repo: None)
    code = main(["--repo", str(tmp_path), "mcp", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert "error" in data and code == 0


def test_status_tolerates_a_hand_edited_partial_report(monkeypatch, capsys, tmp_path):
    # A user (or an older engine) may leave DRIFT.json with missing keys; the
    # prompt path must degrade, never traceback.
    monkeypatch.setattr("engine.core.status.read_status", lambda repo: {"ts": "t"})
    code = main(["--repo", str(tmp_path), "status"])
    out = capsys.readouterr().out
    assert "0 alert(s)" in out and code == 0


# ---- import observed defaults to the host's own snapshot ----


def test_import_observed_defaults_to_the_host_snapshot(monkeypatch, capsys, tmp_path):
    # The CLI computes this path everywhere else; making the user retype it was
    # pure friction. `plane import observed` alone now reads it.
    class _Plat:
        name = "fake"

        def hostname(self):
            return "h"

        def home(self):
            return tmp_path

    monkeypatch.setattr("engine.platform.current_platform", lambda: _Plat())
    inst = tmp_path / "inst"
    (inst / "registry").mkdir(parents=True)
    (inst / ".planeops").write_text("")
    snapdir = inst / "observed" / "h"
    snapdir.mkdir(parents=True)
    (snapdir / "snapshot.json").write_text(
        json.dumps(
            {
                "host": "h",
                "observed": [{"adapter": "manual", "native_id": "x", "facts": {}}],
            }
        )
    )
    assert main(["--repo", str(inst), "import", "observed"]) == 0
    out = capsys.readouterr().out
    assert "manual/x" in out  # proposal printed from the defaulted snapshot


def test_import_other_kinds_still_require_a_path(capsys, tmp_path):
    (tmp_path / ".planeops").write_text("")
    assert main(["--repo", str(tmp_path), "import", "envfile"]) == 1
    assert "path" in capsys.readouterr().err


def test_drift_json_unseeded_emits_a_json_error_object(monkeypatch, capsys, tmp_path):
    # The --json contract holds for every verb: stdout parses as JSON even when
    # the snapshot is missing; the exit code still says operator error.
    def _raise(repo):
        raise FileNotFoundError("no readable snapshot at x; run `plane observe` first")

    monkeypatch.setattr("engine.core.drift.run_drift", _raise)
    code = main(["--repo", str(tmp_path), "drift", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert "error" in data and "plane observe" in data["error"]
    assert code == 1
