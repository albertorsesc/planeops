"""`plane reconcile` wiring: observe then drift, one pass, drift's exit code."""

import pytest

from planeops.cli import main
from tests.cli.helpers import _report


@pytest.fixture
def inst(tmp_path):
    (tmp_path / ".planeops").write_text("")
    return str(tmp_path)


def test_reconcile_observes_then_drifts_and_returns_drift_exit_code(
    monkeypatch, capsys, inst
):
    calls = []
    monkeypatch.setattr(
        "planeops.core.observe.run_observe",
        lambda repo, **k: calls.append("observe") or {"observed": [1, 2], "host": "h"},
    )
    monkeypatch.setattr(
        "planeops.core.drift.run_drift",
        lambda repo: calls.append("drift") or _report(alerts=3),
    )
    code = main(["--repo", inst, "reconcile"])
    assert calls == ["observe", "drift"]  # observe first, then drift on the fresh snap
    out = capsys.readouterr().out
    assert "observed 2" in out and "3 alert(s)" in out
    assert code == 2  # alerts -> non-zero, same as `drift`


def test_reconcile_clean_exits_zero(monkeypatch, inst):
    monkeypatch.setattr(
        "planeops.core.observe.run_observe",
        lambda repo, **k: {"observed": [], "host": "h"},
    )
    monkeypatch.setattr("planeops.core.drift.run_drift", lambda repo: _report(alerts=0))
    assert main(["--repo", inst, "reconcile"]) == 0
