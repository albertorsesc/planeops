"""launchd scheduler backend: pure generation of the reconcile plist + its
governed registry entry."""

from engine.schedulers.launchd import SCHEDULER as LAUNCHD


def test_runs_reconcile_on_interval_and_login(tmp_path):
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
    # a dead reconcile heartbeat should escalate: the adapter sets facts.drifted
    # when the agent is unloaded, and tolerance:alert routes that to an alert.
    assert entry["tolerance"] == "alert"


def test_off_retires_and_drops_run_at_load(tmp_path):
    job = LAUNCHD.build(
        tmp_path, plane="p", path_env="", interval=3600, login=False, off=True
    )
    assert job.entries[0]["lifecycle"] == "retired"
    assert "RunAtLoad" not in next(iter(job.files.values()))
