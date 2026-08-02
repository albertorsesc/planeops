"""Instance resolution at the CLI: no marker means refuse, not adopt.

A bare directory silently adopted as the instance was the trap: a fresh user
running `plane observe` before `plane init` sprayed `observed/` into whatever
directory they stood in. Only `plane init` creates instances; every other verb
refuses an unmarked root.
"""

from planeops.cli import main


def test_unmarked_directory_is_refused_with_the_init_hint(capsys, tmp_path):
    assert main(["--repo", str(tmp_path), "observe"]) == 1
    err = capsys.readouterr().err
    assert "plane init" in err
    assert not (tmp_path / "observed").exists()  # nothing was written


def test_unmarked_refusal_covers_read_verbs_too(capsys, tmp_path):
    assert main(["--repo", str(tmp_path), "status"]) == 1
    assert "plane init" in capsys.readouterr().err


def test_marker_present_resolves_quietly(monkeypatch, capsys, tmp_path):
    (tmp_path / ".planeops").write_text("")
    monkeypatch.setattr(
        "planeops.core.status.read_status",
        lambda repo: {"alert_count": 0, "ts": "t", "summary": {}},
    )
    assert main(["--repo", str(tmp_path), "status"]) == 0
    assert ".planeops" not in capsys.readouterr().err
