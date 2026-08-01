"""Instance resolution at the CLI: the missing-marker note."""

from planeops.cli import main


def test_missing_marker_prints_a_note(monkeypatch, capsys, tmp_path):
    # A bare directory silently adopted as the instance was the trap; the verbs
    # now say so once on stderr (an init-created instance has the marker).
    monkeypatch.setattr(
        "planeops.core.status.read_status",
        lambda repo: {"alert_count": 0, "ts": "t", "summary": {}},
    )
    assert main(["--repo", str(tmp_path), "status"]) == 0
    assert ".planeops" in capsys.readouterr().err


def test_marker_present_prints_no_note(monkeypatch, capsys, tmp_path):
    (tmp_path / ".planeops").write_text("")
    monkeypatch.setattr(
        "planeops.core.status.read_status",
        lambda repo: {"alert_count": 0, "ts": "t", "summary": {}},
    )
    assert main(["--repo", str(tmp_path), "status"]) == 0
    assert ".planeops" not in capsys.readouterr().err
