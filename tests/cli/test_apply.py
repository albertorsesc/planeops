"""`plane apply` wiring: honest no-changes, loud unknown --id, failure exit,
and the post-converge drift refresh."""

import pytest

from engine.cli import main
from engine.core.apply import Applied
from engine.core.contracts import Change, Result
from tests.cli.helpers import _report, _status


@pytest.fixture
def inst(tmp_path):
    (tmp_path / ".planeops").write_text("")
    return str(tmp_path)


def test_apply_unknown_id_is_an_error(monkeypatch, capsys, inst):
    def _raise(repo, *, only_id=None, only_phase=None):
        raise LookupError("no registry entry with id 'launchd/typo'")

    monkeypatch.setattr("engine.core.apply.run_apply", _raise)
    code = main(["--repo", inst, "apply", "--id", "launchd/typo"])
    assert code == 1
    assert "launchd/typo" in capsys.readouterr().err


def test_apply_no_changes_reports_remaining_drift(monkeypatch, capsys, inst):
    # "no changes to apply; machine matches desired state" lied whenever drift had
    # alerts that no adapter could plan away (service file absent, uncovered,
    # owner: human). The message must be neutral and surface the standing alerts.
    monkeypatch.setattr(
        "engine.core.apply.run_apply", lambda repo, *, only_id=None, only_phase=None: []
    )
    monkeypatch.setattr("engine.core.status.read_status", lambda repo: _status(2))
    code = main(["--repo", inst, "apply"])
    out = capsys.readouterr().out
    assert "machine matches desired state" not in out
    assert "no changes planned" in out
    assert "2 alert(s)" in out
    assert code == 0


def test_apply_refreshes_drift_after_execute(monkeypatch, inst):
    # After a converge, DRIFT.json used to stay stale (only observe re-ran), so the
    # shell prompt kept the pre-apply alert count for up to a scheduler interval.
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
    code = main(["--repo", inst, "apply"])
    assert calls == ["observe", "drift"]  # panes recomputed, prompt is fresh
    assert code == 0


def test_apply_failed_execute_exits_1(monkeypatch, capsys, inst):
    failed = Applied(
        Change("x/y", "configure", "d", {}), True, Result(ok=False, detail="boom")
    )
    monkeypatch.setattr(
        "engine.core.apply.run_apply",
        lambda repo, *, only_id=None, only_phase=None: [failed],
    )
    monkeypatch.setattr(
        "engine.core.observe.run_observe",
        lambda repo: {"observed": [], "uncovered": [], "host": "h"},
    )
    monkeypatch.setattr("engine.core.drift.run_drift", lambda repo: _report())
    assert main(["--repo", inst, "apply"]) == 1
    assert "FAILED" in capsys.readouterr().out
