import os
import plistlib
from datetime import datetime

from engine.adapters.launchd import (
    ADAPTER,
    LaunchdAdapter,
    RunResult,
    parse_launchctl_list,
)
from engine.core.contracts import Change, Ctx, can_apply
from engine.core.schema import entry_from_dict

# Recorded from a real `launchctl list`, then trimmed to representative rows.
LAUNCHCTL = (
    "PID\tStatus\tLabel\n"
    "693\t0\tcom.apple.Finder\n"
    "-\t0\tai.example.loaded-not-running\n"
    "4242\t0\tai.example.running\n"
)


def _list_run(cmd):
    return RunResult(0, LAUNCHCTL, "")


class RecordingRun:
    """Captures commands and returns a canned exit code, for execute tests."""

    def __init__(self, code=0, err=""):
        self.calls = []
        self.code = code
        self.err = err

    def __call__(self, cmd):
        self.calls.append(cmd)
        return RunResult(self.code, "", self.err)


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


def _entry(entry_id, lifecycle):
    return entry_from_dict(
        {
            "id": entry_id,
            "adapter": "launchd",
            "domain": "service",
            "lifecycle": lifecycle,
            "intent": "i",
        }
    )


def _obs(label, *, loaded, pid=None, plist_path="/tmp/x.plist"):
    from engine.core.contracts import Observed

    return Observed(
        "launchd", label, {"loaded": loaded, "pid": pid, "plist_path": plist_path}
    )


# ---- observe -------------------------------------------------------------


def test_parse_launchctl_list_skips_header_and_reads_pids():
    jobs = parse_launchctl_list(LAUNCHCTL)
    assert jobs["ai.example.running"] == 4242
    assert jobs["ai.example.loaded-not-running"] is None
    assert "PID" not in jobs


def test_observe_reports_loaded_and_running(tmp_path, fake_platform):
    _write_plist(tmp_path, "ai.example.running")
    _write_plist(tmp_path, "ai.example.loaded-not-running")
    _write_plist(tmp_path, "ai.example.unloaded")  # absent from launchctl list
    out = {
        o.native_id: o
        for o in LaunchdAdapter(run=_list_run).observe(_ctx(fake_platform(tmp_path)))
    }
    assert out["ai.example.running"].facts["running"] is True
    assert out["ai.example.running"].facts["pid"] == 4242
    assert out["ai.example.loaded-not-running"].facts["running"] is False
    assert out["ai.example.unloaded"].facts["loaded"] is False


def test_observed_key_matches_entry_id_convention(tmp_path, fake_platform):
    _write_plist(tmp_path, "ai.example.running")
    out = LaunchdAdapter(run=_list_run).observe(_ctx(fake_platform(tmp_path)))
    assert out[0].key == "launchd/ai.example.running"


def test_missing_agents_dir_is_empty_not_error(tmp_path, fake_platform):
    assert LaunchdAdapter(run=_list_run).observe(_ctx(fake_platform(tmp_path))) == []


def test_unreadable_plist_degrades_to_filename(tmp_path, fake_platform):
    d = tmp_path / "Library" / "LaunchAgents"
    d.mkdir(parents=True)
    (d / "ai.example.broken.plist").write_text("not a plist")
    out = LaunchdAdapter(run=_list_run).observe(_ctx(fake_platform(tmp_path)))
    assert out[0].native_id == "ai.example.broken"


# ---- plan ----------------------------------------------------------------


def test_launchd_is_a_mutating_adapter():
    assert can_apply(ADAPTER)


def test_plan_retired_but_loaded_proposes_bootout():
    changes = ADAPTER.plan(
        _entry("launchd/svc", "retired"), _obs("svc", loaded=True, pid=99)
    )
    assert len(changes) == 1
    assert changes[0].kind == "remove"
    assert changes[0].action == {
        "op": "bootout",
        "label": "svc",
        "plist_path": "/tmp/x.plist",
        "delete_plist": False,
    }


def test_plan_purge_also_deletes_plist():
    changes = ADAPTER.plan(_entry("launchd/svc", "purge"), _obs("svc", loaded=True))
    assert changes[0].action["delete_plist"] is True
    assert "delete its plist" in changes[0].diff


def test_plan_active_but_unloaded_proposes_bootstrap():
    changes = ADAPTER.plan(_entry("launchd/svc", "active"), _obs("svc", loaded=False))
    assert len(changes) == 1 and changes[0].kind == "configure"
    assert changes[0].action["op"] == "bootstrap"


def test_plan_conformant_states_propose_nothing():
    assert ADAPTER.plan(_entry("launchd/svc", "active"), _obs("svc", loaded=True)) == []
    assert (
        ADAPTER.plan(_entry("launchd/svc", "retired"), _obs("svc", loaded=False)) == []
    )
    assert ADAPTER.plan(_entry("launchd/svc", "active"), None) == []


# ---- execute -------------------------------------------------------------


def test_execute_bootout_calls_launchctl_and_reports_ok():
    rec = RecordingRun(code=0)
    change = Change(
        "launchd/svc",
        "remove",
        "d",
        {"op": "bootout", "label": "svc", "delete_plist": False},
    )
    res = LaunchdAdapter(run=rec).execute(change, _ctx(None))
    assert res.ok
    assert rec.calls == [["launchctl", "bootout", f"gui/{os.getuid()}/svc"]]


def test_execute_bootout_failure_is_reported():
    rec = RecordingRun(code=1, err="No such process")
    change = Change("launchd/svc", "remove", "d", {"op": "bootout", "label": "svc"})
    res = LaunchdAdapter(run=rec).execute(change, _ctx(None))
    assert not res.ok and "failed" in res.detail


def test_execute_purge_deletes_plist(tmp_path):
    plist = tmp_path / "svc.plist"
    plist.write_text("<plist/>")
    change = Change(
        "launchd/svc",
        "remove",
        "d",
        {
            "op": "bootout",
            "label": "svc",
            "plist_path": str(plist),
            "delete_plist": True,
        },
    )
    res = LaunchdAdapter(run=RecordingRun(code=0)).execute(change, _ctx(None))
    assert res.ok and not plist.exists()


def test_execute_bootstrap_calls_launchctl():
    rec = RecordingRun(code=0)
    change = Change(
        "launchd/svc",
        "configure",
        "d",
        {"op": "bootstrap", "label": "svc", "plist_path": "/p.plist"},
    )
    res = LaunchdAdapter(run=rec).execute(change, _ctx(None))
    assert res.ok
    assert rec.calls == [["launchctl", "bootstrap", f"gui/{os.getuid()}", "/p.plist"]]
