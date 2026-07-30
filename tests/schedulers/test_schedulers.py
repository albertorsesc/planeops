"""Scheduler backends: pure generation of the OS reconcile job + its registry entry,
plus the `plane schedule` CLI wiring and `--every` parsing.
"""

import pytest
import yaml

from engine.cli import _parse_every, main
from engine.schedulers import discover_schedulers
from engine.schedulers.launchd import SCHEDULER as LAUNCHD
from engine.schedulers.systemd import SCHEDULER as SYSTEMD


def test_discovery_finds_both_backends_selected_by_platform():
    by_name = {s.name: s for s in discover_schedulers()}
    assert "launchd" in by_name and "systemd" in by_name
    assert "darwin" in by_name["launchd"].sys_platforms
    assert "linux" in by_name["systemd"].sys_platforms


def test_launchd_runs_reconcile_on_interval_and_login(tmp_path):
    job = LAUNCHD.build(
        tmp_path, plane="/bin/plane", path_env="/usr/bin:/x",
        interval=21600, login=True, off=False,
    )  # fmt: skip
    (path, content) = next(iter(job.files.items()))
    assert path == tmp_path / "Library/LaunchAgents/ai.planeops.reconcile.plist"
    assert "<string>reconcile</string>" in content and "/bin/plane" in content
    assert "StartInterval" in content and "21600" in content
    assert "RunAtLoad" in content and "/usr/bin:/x" in content  # PATH baked in
    [entry] = job.entries
    assert entry["id"] == "launchd/ai.planeops.reconcile"
    assert entry["lifecycle"] == "active" and entry["adapter"] == "launchd"
    # a dead reconcile heartbeat should escalate: the adapter sets facts.drifted when
    # the agent is unloaded, and tolerance:alert routes that to an alert (not a report).
    assert entry["tolerance"] == "alert"


def test_launchd_off_retires_and_drops_run_at_load(tmp_path):
    job = LAUNCHD.build(
        tmp_path, plane="p", path_env="", interval=3600, login=False, off=True
    )
    assert job.entries[0]["lifecycle"] == "retired"
    assert "RunAtLoad" not in next(iter(job.files.values()))


def test_systemd_pairs_timer_and_service_and_unmanages_the_service(tmp_path):
    job = SYSTEMD.build(
        tmp_path, plane="/x/plane", path_env="/p",
        interval=21600, login=True, off=False,
    )  # fmt: skip
    assert sorted(p.name for p in job.files) == [
        "planeops-reconcile.service",
        "planeops-reconcile.timer",
    ]
    timer = next(c for p, c in job.files.items() if p.name.endswith(".timer"))
    assert "OnUnitActiveSec=21600s" in timer and "OnBootSec" in timer
    svc = next(c for p, c in job.files.items() if p.name.endswith(".service"))
    assert "ExecStart=/x/plane reconcile" in svc and "Environment=PATH=/p" in svc
    assert job.entries[0]["id"] == "systemd/planeops-reconcile.timer"
    assert job.entries[0]["tolerance"] == "alert"  # dead-heartbeat escalates
    # the timer-driven oneshot is bundled but not governed on its own
    assert job.globs == [{"glob": "systemd/planeops-reconcile.service"}]


@pytest.mark.parametrize("s,secs", [("6h", 21600), ("30m", 1800), ("90s", 90)])
def test_parse_every_accepts_durations(s, secs):
    assert _parse_every(s) == secs


@pytest.mark.parametrize("bad", ["6", "6d", "0h", "abc", "-1h", ""])
def test_parse_every_rejects_junk(bad):
    with pytest.raises(ValueError):
        _parse_every(bad)


class _FakePlat:
    name = "fake"

    def __init__(self, home):
        self._home = home

    def home(self):
        return self._home

    def hostname(self):
        return "h"


def _stub_observe(monkeypatch):
    # schedule refreshes the snapshot after writing the job; stub the scan so the
    # test never runs real adapters against the live machine.
    monkeypatch.setattr(
        "engine.core.observe.run_observe",
        lambda repo: {"observed": [], "uncovered": [], "host": "h"},
    )


def test_cli_schedule_writes_files_and_declares_the_entry(tmp_path, monkeypatch):
    # current_platform().home() is faked to a tmp dir, so the real ~/Library or
    # ~/.config is never written. The host's backend (launchd on mac / systemd on
    # Linux CI) is used, both write files + declare an active entry.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("engine.platform.current_platform", lambda: _FakePlat(home))
    _stub_observe(monkeypatch)
    inst = tmp_path / "inst"
    (inst / "registry").mkdir(parents=True)
    (inst / ".planeops").write_text("")

    assert main(["--repo", str(inst), "schedule", "--every", "6h"]) == 0
    doc = yaml.safe_load((inst / "registry" / "schedule.yaml").read_text())
    assert doc["entries"][0]["lifecycle"] == "active"
    assert list(home.rglob("*.plist")) or list(
        home.rglob("*.timer")
    )  # a job file written


def test_cli_schedule_off_declares_a_retired_entry(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("engine.platform.current_platform", lambda: _FakePlat(home))
    _stub_observe(monkeypatch)
    inst = tmp_path / "inst"
    (inst / "registry").mkdir(parents=True)
    (inst / ".planeops").write_text("")

    assert main(["--repo", str(inst), "schedule", "--off"]) == 0
    doc = yaml.safe_load((inst / "registry" / "schedule.yaml").read_text())
    assert doc["entries"][0]["lifecycle"] == "retired"


def test_cli_schedule_rejects_a_bad_interval(tmp_path):
    (tmp_path / ".planeops").write_text("")
    assert main(["--repo", str(tmp_path), "schedule", "--every", "banana"]) == 1
