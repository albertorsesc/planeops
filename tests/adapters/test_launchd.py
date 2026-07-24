import plistlib
from datetime import datetime

from engine.adapters.launchd import ADAPTER, LaunchdAdapter, parse_launchctl_list
from engine.core.contracts import Ctx

# Recorded from a real `launchctl list`, then trimmed to representative rows.
LAUNCHCTL = (
    "PID\tStatus\tLabel\n"
    "693\t0\tcom.apple.Finder\n"
    "-\t0\tai.example.loaded-not-running\n"
    "4242\t0\tai.example.running\n"
)


def _ctx(platform):
    return Ctx(platform=platform, host="testhost", now=datetime(2026, 7, 22))


def _write_plist(root, label, *, keepalive=True, run_at_load=False):
    d = root / "Library" / "LaunchAgents"
    d.mkdir(parents=True, exist_ok=True)
    payload = {"Label": label, "ProgramArguments": ["/bin/echo", "hi"]}
    if keepalive:
        payload["KeepAlive"] = True
    if run_at_load:
        payload["RunAtLoad"] = True
    with (d / f"{label}.plist").open("wb") as fh:
        plistlib.dump(payload, fh)


def test_parse_launchctl_list_skips_header_and_reads_pids():
    jobs = parse_launchctl_list(LAUNCHCTL)
    assert jobs["ai.example.running"] == 4242
    assert jobs["ai.example.loaded-not-running"] is None
    assert "PID" not in jobs


def test_observe_reports_loaded_and_running(tmp_path, fake_platform):
    _write_plist(tmp_path, "ai.example.running")
    _write_plist(tmp_path, "ai.example.loaded-not-running")
    _write_plist(tmp_path, "ai.example.unloaded")  # absent from launchctl list
    adapter = LaunchdAdapter(run=lambda cmd: LAUNCHCTL)

    out = {o.native_id: o for o in adapter.observe(_ctx(fake_platform(tmp_path)))}
    assert out["ai.example.running"].facts["running"] is True
    assert out["ai.example.running"].facts["pid"] == 4242
    assert out["ai.example.loaded-not-running"].facts["loaded"] is True
    assert out["ai.example.loaded-not-running"].facts["running"] is False
    assert out["ai.example.unloaded"].facts["loaded"] is False


def test_observed_key_matches_entry_id_convention(tmp_path, fake_platform):
    _write_plist(tmp_path, "ai.example.running")
    out = LaunchdAdapter(run=lambda cmd: LAUNCHCTL).observe(_ctx(fake_platform(tmp_path)))
    assert out[0].key == "launchd/ai.example.running"


def test_keepalive_and_run_at_load_are_read(tmp_path, fake_platform):
    _write_plist(tmp_path, "ai.example.svc", keepalive=True, run_at_load=True)
    out = LaunchdAdapter(run=lambda cmd: LAUNCHCTL).observe(_ctx(fake_platform(tmp_path)))
    assert out[0].facts["keepalive"] is True
    assert out[0].facts["run_at_load"] is True


def test_missing_agents_dir_is_empty_not_error(tmp_path, fake_platform):
    assert LaunchdAdapter(run=lambda cmd: LAUNCHCTL).observe(_ctx(fake_platform(tmp_path))) == []


def test_unreadable_plist_degrades_to_filename(tmp_path, fake_platform):
    d = tmp_path / "Library" / "LaunchAgents"
    d.mkdir(parents=True)
    (d / "ai.example.broken.plist").write_text("not a plist")
    out = LaunchdAdapter(run=lambda cmd: LAUNCHCTL).observe(_ctx(fake_platform(tmp_path)))
    assert out[0].native_id == "ai.example.broken"


def test_launchd_is_observe_only():
    assert not hasattr(ADAPTER, "execute")
    assert not hasattr(ADAPTER, "plan")
