import os
import plistlib
from datetime import datetime

from planeops._run import RunResult
from planeops.adapters.launchd import (
    ADAPTER,
    LaunchdAdapter,
    parse_launchctl_list,
)
from planeops.core.contracts import Change, Ctx, can_apply
from planeops.core.schema import entry_from_dict

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
    """Captures commands (and the per-call timeout) and returns a canned exit
    code, for execute tests."""

    def __init__(self, code=0, err=""):
        self.calls = []
        self.timeouts = []
        self.code = code
        self.err = err

    def __call__(self, cmd, *, timeout=30):
        self.calls.append(cmd)
        self.timeouts.append(timeout)
        return RunResult(self.code, "", self.err)


def _ctx(platform):
    return Ctx(platform=platform, host="testhost", now=datetime(2026, 7, 22))


def _write_plist(
    root, label, *, keepalive=True, run_at_load=False, start_interval=None
):
    d = root / "Library" / "LaunchAgents"
    d.mkdir(parents=True, exist_ok=True)
    payload = {"Label": label, "ProgramArguments": ["/bin/echo", "hi"]}
    if keepalive:
        payload["KeepAlive"] = True
    if run_at_load:
        payload["RunAtLoad"] = True
    if start_interval is not None:
        payload["StartInterval"] = start_interval
    with (d / f"{label}.plist").open("wb") as fh:
        plistlib.dump(payload, fh)


def _observe_facts(root, fake_platform):
    return {
        o.native_id: o.facts
        for o in LaunchdAdapter(run=_list_run).observe(_ctx(fake_platform(root)))
    }


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
    from planeops.core.contracts import Observed

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


# ---- observe: dead-heartbeat drift (a persistent agent that is not loaded) ----


def test_observe_flags_drift_when_a_load_at_login_agent_is_unloaded(
    tmp_path, fake_platform
):
    # RunAtLoad says "load me at login", but the agent is absent from `launchctl list`:
    # it drifted from its own definition. This is the dead-heartbeat signal a scheduled
    # reconcile agent needs, since its whole job is to keep drift fresh.
    _write_plist(tmp_path, "ai.example.dead", keepalive=False, run_at_load=True)
    assert _observe_facts(tmp_path, fake_platform)["ai.example.dead"]["drifted"] is True


def test_observe_flags_drift_when_an_interval_agent_is_unloaded(
    tmp_path, fake_platform
):
    # No RunAtLoad, but a StartInterval agent must be loaded to fire; unloaded it never
    # runs again, so a `--no-login` schedule is covered too.
    _write_plist(tmp_path, "ai.example.interval", keepalive=False, start_interval=3600)
    got = _observe_facts(tmp_path, fake_platform)["ai.example.interval"]
    assert got["drifted"] is True


def test_observe_no_drift_for_an_on_demand_agent_that_is_unloaded(
    tmp_path, fake_platform
):
    # Neither RunAtLoad/KeepAlive nor a schedule: an on-demand agent being unloaded is
    # normal, not drift.
    _write_plist(tmp_path, "ai.example.ondemand", keepalive=False)
    got = _observe_facts(tmp_path, fake_platform)["ai.example.ondemand"]
    assert got["drifted"] is False


def test_observe_no_drift_when_a_persistent_agent_is_loaded(tmp_path, fake_platform):
    _write_plist(
        tmp_path, "ai.example.running", run_at_load=True
    )  # loaded per LAUNCHCTL
    got = _observe_facts(tmp_path, fake_platform)["ai.example.running"]
    assert got["drifted"] is False


# ---- plan ----------------------------------------------------------------


class _Plat:
    """Minimal Platform stub: plan/execute receive a real ctx, per the contract."""

    name = "fake"

    def hostname(self):
        return "testhost"

    def home(self):
        from pathlib import Path

        return Path("/home/fake")


def test_launchd_is_a_mutating_adapter():
    assert can_apply(ADAPTER)


def test_plan_retired_but_loaded_proposes_bootout():
    changes = ADAPTER.plan(
        _entry("launchd/svc", "retired"),
        _obs("svc", loaded=True, pid=99),
        _ctx(_Plat()),
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
    changes = ADAPTER.plan(
        _entry("launchd/svc", "purge"), _obs("svc", loaded=True), _ctx(_Plat())
    )
    assert changes[0].action["delete_plist"] is True
    assert "delete its plist" in changes[0].diff


def test_plan_active_but_unloaded_proposes_bootstrap():
    changes = ADAPTER.plan(
        _entry("launchd/svc", "active"), _obs("svc", loaded=False), _ctx(_Plat())
    )
    assert len(changes) == 1 and changes[0].kind == "configure"
    assert changes[0].action["op"] == "bootstrap"


def test_plan_conformant_states_propose_nothing():
    ctx = _ctx(_Plat())
    assert (
        ADAPTER.plan(_entry("launchd/svc", "active"), _obs("svc", loaded=True), ctx)
        == []
    )
    assert (
        ADAPTER.plan(_entry("launchd/svc", "retired"), _obs("svc", loaded=False), ctx)
        == []
    )
    assert ADAPTER.plan(_entry("launchd/svc", "active"), None, ctx) == []


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
    # Service ops are quick; a bounded ceiling keeps a hung launchctl from
    # wedging the whole apply run (unlike unbounded package installs).
    assert rec.timeouts == [LaunchdAdapter.EXECUTE_TIMEOUT] and rec.timeouts[0] == 300


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


def test_observe_marks_always_on_for_persistent_agents(tmp_path, fake_platform):
    # always_on feeds drift's ungoverned pass: an undeclared agent that will run
    # code (login/keepalive/interval) alerts; a plain on-demand one only reports.
    _write_plist(tmp_path, "ai.example.dead", keepalive=False, run_at_load=True)
    _write_plist(tmp_path, "ai.example.ondemand", keepalive=False)
    facts = _observe_facts(tmp_path, fake_platform)
    assert facts["ai.example.dead"]["always_on"] is True
    assert facts["ai.example.ondemand"]["always_on"] is False


def test_observe_present_means_loaded(tmp_path, fake_platform):
    # Semantic presence for a service is "loaded", not "file on disk": drift's
    # retired check consumes this, so a booted-out agent stops alerting.
    _write_plist(tmp_path, "ai.example.running")
    _write_plist(tmp_path, "ai.example.unloaded", keepalive=False)
    facts = _observe_facts(tmp_path, fake_platform)
    assert facts["ai.example.running"]["present"] is True
    assert facts["ai.example.unloaded"]["present"] is False


def test_parked_service_is_left_exactly_as_found():
    # `parked` means keep-as-is: never bootstrap an unloaded parked agent
    # (a freshly seeded vendor updater must not get a bootstrap proposal), and
    # never bootout a loaded one.
    ctx = _ctx(_Plat())
    assert (
        ADAPTER.plan(_entry("launchd/idle", "parked"), _obs("idle", loaded=False), ctx)
        == []
    )
    assert (
        ADAPTER.plan(
            _entry("launchd/run", "parked"), _obs("run", loaded=True, pid=7), ctx
        )
        == []
    )


def test_observe_reports_the_plists_log_paths(tmp_path, fake_platform):
    # The plist itself declares where the service logs; the observation carries
    # it so seeding can land `logs:` in the manifest without hand-hunting.
    d = tmp_path / "Library" / "LaunchAgents"
    d.mkdir(parents=True)
    payload = {
        "Label": "com.x.logged",
        "ProgramArguments": ["/bin/echo"],
        "StandardOutPath": "/tmp/x/out.log",
        "StandardErrorPath": "/tmp/x/err.log",
    }
    with (d / "com.x.logged.plist").open("wb") as fh:
        plistlib.dump(payload, fh)
    facts = _observe_facts(tmp_path, fake_platform)
    assert facts["com.x.logged"]["logs"] == ["/tmp/x/out.log", "/tmp/x/err.log"]


def test_observe_omits_logs_when_the_plist_declares_none(tmp_path, fake_platform):
    _write_plist(tmp_path, "com.x.quiet")
    facts = _observe_facts(tmp_path, fake_platform)
    assert "logs" not in facts["com.x.quiet"]


# ---- the publisher an agent's program is signed by ----

# `codesign -dv` writes to stderr, and reports `TeamIdentifier=not set` for a
# binary the OS ships. Shape recorded from a real run; the vendor is invented.
VENDOR_SIGNATURE = (
    "Executable=/Applications/Example.app/Contents/MacOS/ExampleUpdater\n"
    "Identifier=com.example.updater\n"
    "Authority=Developer ID Application: Example Corp (ABCDE12345)\n"
    "TeamIdentifier=ABCDE12345\n"
)
OS_SIGNATURE = (
    "Executable=/bin/sh\nAuthority=macOS Software Signing\nTeamIdentifier=not set\n"
)


def _run_with_signature(signature):
    def run(cmd, **kw):
        if cmd[0] == "codesign":
            return RunResult(0, "", signature)
        return RunResult(0, LAUNCHCTL, "")

    return run


def _facts_with_signature(root, fake_platform, signature):
    adapter = LaunchdAdapter(run=_run_with_signature(signature))
    return {o.native_id: o.facts for o in adapter.observe(_ctx(fake_platform(root)))}


def test_observe_reports_the_team_its_program_is_signed_by(tmp_path, fake_platform):
    # The publisher is what makes a vendor exemption safe: a Team ID is issued by
    # Apple, so unlike a label it is not something the plist's author picks.
    _write_plist(tmp_path, "com.vendor.updater")
    facts = _facts_with_signature(tmp_path, fake_platform, VENDOR_SIGNATURE)
    assert facts["com.vendor.updater"]["publisher"] == "ABCDE12345"


def test_a_program_the_os_ships_has_no_publisher(tmp_path, fake_platform):
    # The OS signs every interpreter, so an agent running `/bin/sh -c payload`
    # must not inherit a publisher: that is the bypass this exists to refuse.
    _write_plist(tmp_path, "com.x.shell")
    facts = _facts_with_signature(tmp_path, fake_platform, OS_SIGNATURE)
    assert "publisher" not in facts["com.x.shell"]


def test_an_unsigned_program_has_no_publisher(tmp_path, fake_platform):
    def run(cmd, **kw):
        if cmd[0] == "codesign":
            return RunResult(1, "", "/x: code object is not signed at all\n")
        return RunResult(0, LAUNCHCTL, "")

    _write_plist(tmp_path, "com.x.unsigned")
    adapter = LaunchdAdapter(run=run)
    facts = {
        o.native_id: o.facts for o in adapter.observe(_ctx(fake_platform(tmp_path)))
    }
    assert "publisher" not in facts["com.x.unsigned"]


def test_a_plist_with_no_program_is_not_signature_checked(tmp_path, fake_platform):
    d = tmp_path / "Library" / "LaunchAgents"
    d.mkdir(parents=True, exist_ok=True)
    with (d / "com.x.bare.plist").open("wb") as fh:
        plistlib.dump({"Label": "com.x.bare", "KeepAlive": True}, fh)

    calls = []

    def run(cmd, **kw):
        calls.append(cmd[0])
        return RunResult(0, LAUNCHCTL, "")

    facts = {
        o.native_id: o.facts
        for o in LaunchdAdapter(run=run).observe(_ctx(fake_platform(tmp_path)))
    }
    assert "publisher" not in facts["com.x.bare"]
    assert "codesign" not in calls
