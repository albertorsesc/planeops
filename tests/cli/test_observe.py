"""`plane observe` wiring: the summary line and failed-adapter warnings."""

import pytest

from planeops.cli import main


@pytest.fixture
def inst(tmp_path):
    (tmp_path / ".planeops").write_text("")
    return str(tmp_path)


def test_observe_warns_about_failed_adapter_scans(monkeypatch, capsys, inst):
    monkeypatch.setattr(
        "planeops.core.observe.run_observe",
        lambda repo, attest=False: {
            "observed": [],
            "uncovered": [],
            "host": "h",
            "failed": [{"adapter": "pkg-brew", "error": "boom"}],
        },
    )
    assert main(["--repo", inst, "observe"]) == 0
    err = capsys.readouterr().err
    assert "pkg-brew" in err and "failed" in err
