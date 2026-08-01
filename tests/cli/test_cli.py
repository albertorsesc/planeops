"""The package seam: dispatch and the central operator-error choke point.
Per-verb behavior lives in the sibling per-verb files."""

import pytest

from planeops.cli import main


@pytest.fixture
def inst(tmp_path):
    (tmp_path / ".planeops").write_text("")
    return str(tmp_path)


def _schema_boom(*a, **k):
    from planeops.core.schema import SchemaError

    raise SchemaError("entry 'x': lifecycle=nope is not one of: active, ...")


def test_observe_schema_error_is_clean_exit_1(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.observe.run_observe", _schema_boom)
    assert main(["--repo", inst, "observe"]) == 1
    assert "lifecycle=nope" in capsys.readouterr().err  # message, not a traceback


def test_drift_schema_error_is_clean_exit_1(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.drift.run_drift", _schema_boom)
    assert main(["--repo", inst, "drift"]) == 1
    assert "lifecycle=nope" in capsys.readouterr().err


def test_apply_schema_error_is_clean_exit_1(monkeypatch, capsys, inst):
    monkeypatch.setattr("planeops.core.apply.run_apply", _schema_boom)
    assert main(["--repo", inst, "apply"]) == 1
    assert "lifecycle=nope" in capsys.readouterr().err
