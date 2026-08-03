"""`plane schedule` wiring: interval grammar, confirm gate, warnings, and the
post-write observe. Backend generation lives in tests/schedulers/."""

import pytest

from planeops.cli import main
from planeops.cli.schedule import _parse_every
from planeops.providers import yaml


@pytest.mark.parametrize("s,secs", [("6h", 21600), ("30m", 1800), ("90s", 90)])
def test_parse_every_accepts_durations(s, secs):
    assert _parse_every(s) == secs


@pytest.mark.parametrize("bad", ["6", "6d", "0h", "abc", "-1h", ""])
def test_parse_every_rejects_junk(bad):
    with pytest.raises(ValueError):
        _parse_every(bad)


class _Plat:
    name = "fake"

    def __init__(self, home):
        self._home = home

    def home(self):
        return self._home

    def hostname(self):
        return "h"


@pytest.fixture
def sched(tmp_path, monkeypatch):
    """A faked home + a marked instance + a stubbed observe, so the host's real
    ~/Library or ~/.config is never written and no real adapter runs."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("planeops.platform.current_platform", lambda: _Plat(home))
    monkeypatch.setattr(
        "planeops.core.observe.run_observe",
        lambda repo: {"observed": [], "uncovered": [], "host": "h"},
    )
    inst = tmp_path / "inst"
    (inst / "registry").mkdir(parents=True)
    (inst / ".planeops").write_text("")
    return home, inst


def test_schedule_writes_files_and_declares_the_entry(sched):
    home, inst = sched
    assert main(["--repo", str(inst), "schedule", "--every", "6h", "--yes"]) == 0
    doc = yaml.load((inst / "registry" / "schedule.yaml").read_text())
    assert doc["entries"][0]["lifecycle"] == "active"
    # exactly ONE backend's files land, never both (selection, not fallthrough)
    wrote_plist = bool(list(home.rglob("*.plist")))
    wrote_timer = bool(list(home.rglob("*.timer")))
    assert wrote_plist != wrote_timer


def test_schedule_off_declares_a_retired_entry(sched):
    home, inst = sched
    assert main(["--repo", str(inst), "schedule", "--off", "--yes"]) == 0
    doc = yaml.load((inst / "registry" / "schedule.yaml").read_text())
    assert doc["entries"][0]["lifecycle"] == "retired"


def test_schedule_rejects_a_bad_interval(tmp_path):
    (tmp_path / ".planeops").write_text("")
    assert main(["--repo", str(tmp_path), "schedule", "--every", "banana"]) == 1


def test_schedule_asks_before_writing_and_yes_skips(sched, capsys):
    # schedule writes machine state; like `import --write`, it must show what it
    # will write and confirm. No readable stdin and no --yes: write nothing.
    home, inst = sched
    assert main(["--repo", str(inst), "schedule", "--every", "6h"]) == 0
    captured = capsys.readouterr()
    assert "not written" in captured.err and "--yes" in captured.err
    # The preview shows the governed entry's content, not just file paths.
    assert "lifecycle: active" in captured.out
    assert not list(home.rglob("*.plist")) and not list(home.rglob("*.timer"))
    assert not (inst / "registry" / "schedule.yaml").exists()

    assert main(["--repo", str(inst), "schedule", "--every", "6h", "--yes"]) == 0
    assert (inst / "registry" / "schedule.yaml").exists()


def test_schedule_warns_when_plane_is_not_installed(sched, monkeypatch, capsys):
    # The job would silently fail at fire time if the baked binary path does not
    # exist; say so at schedule time instead.
    home, inst = sched
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert main(["--repo", str(inst), "schedule", "--yes"]) == 0
    assert "not on PATH" in capsys.readouterr().err


def test_schedule_observes_after_writing(sched, monkeypatch):
    # `plane apply` plans from the snapshot; without a refresh the just-written
    # timer file is invisible and apply says "no changes planned" on first use.
    home, inst = sched
    seen = []
    monkeypatch.setattr(
        "planeops.core.observe.run_observe",
        lambda repo: (
            seen.append(repo) or {"observed": [], "uncovered": [], "host": "h"}
        ),
    )
    assert main(["--repo", str(inst), "schedule", "--every", "6h", "--yes"]) == 0
    assert seen == [inst.resolve()]


def test_schedule_confirms_when_the_job_lands_in_the_snapshot(
    sched, monkeypatch, capsys
):
    home, inst = sched
    monkeypatch.setattr(
        "planeops.core.observe.run_observe",
        lambda repo: {
            "observed": [
                {"adapter": e.split("/", 1)[0], "native_id": e.split("/", 1)[1]}
                for e in (
                    "launchd/ai.planeops.reconcile",
                    "systemd/planeops-reconcile.timer",
                )
            ],
            "uncovered": [],
            "host": "h",
        },
    )
    assert main(["--repo", str(inst), "schedule", "--every", "6h", "--yes"]) == 0
    assert "the new job is in the snapshot" in capsys.readouterr().out


def test_schedule_warns_when_the_job_did_not_land_in_the_snapshot(sched, capsys):
    # The fixture's stubbed observe returns nothing: the success message must
    # not claim "the new job is in the snapshot" (verifiably false with a
    # broken user bus); warn and point at the fix instead.
    home, inst = sched
    assert main(["--repo", str(inst), "schedule", "--every", "6h", "--yes"]) == 0
    out = capsys.readouterr()
    assert "did not appear in the snapshot" in out.err
    assert "the new job is in the snapshot" not in out.out
