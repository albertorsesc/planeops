from datetime import datetime

from planeops._run import RunResult
from planeops.adapters.pkg_brew import ADAPTER, PkgBrewAdapter, parse_brew_versions
from planeops.core.contracts import Change, Ctx, Observed, can_apply
from planeops.core.schema import entry_from_dict

# Recorded from `brew list --versions --formula`, trimmed to representative rows.
BREW_VERSIONS = "git 2.45.2\nripgrep 14.1.0\npython@3.12 3.12.4 3.12.5\n"


def _run_ok(cmd):
    return RunResult(0, BREW_VERSIONS, "")


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


class _Plat:
    """Minimal Platform stub: `plan`/`execute` receive a real ctx, matching the
    contract (the engine never passes platform=None)."""

    name = "fake"

    def hostname(self):
        return "testhost"

    def home(self):
        from pathlib import Path

        return Path("/home/fake")


def _ctx():
    return Ctx(platform=_Plat(), host="testhost", now=datetime(2026, 7, 27))


def _entry(entry_id, lifecycle):
    return entry_from_dict(
        {
            "id": entry_id,
            "adapter": "pkg-brew",
            "domain": "package",
            "lifecycle": lifecycle,
            "intent": "i",
        }
    )


def _obs(name, version="1.0.0"):
    return Observed("pkg-brew", name, {}, version=version)


# ---- parse / observe -----------------------------------------------------


def test_parse_brew_versions_reads_name_and_latest_version():
    v = parse_brew_versions(BREW_VERSIONS)
    assert v["git"] == "2.45.2"
    assert v["ripgrep"] == "14.1.0"
    assert v["python@3.12"] == "3.12.5"  # last version when several are installed


def test_observe_reports_formulae_with_versions():
    out = {o.native_id: o for o in PkgBrewAdapter(run=_run_ok).observe(_ctx())}
    assert out["ripgrep"].version == "14.1.0"
    assert out["ripgrep"].key == "pkg-brew/ripgrep"


def test_observe_degrades_when_brew_absent():
    def fail(cmd):
        return RunResult(127, "", "command not found: brew")

    assert PkgBrewAdapter(run=fail).observe(_ctx()) == []


# ---- plan ----------------------------------------------------------------


def test_pkg_brew_is_a_mutating_adapter():
    assert can_apply(ADAPTER)


def test_plan_active_but_absent_proposes_install():
    changes = ADAPTER.plan(_entry("pkg-brew/ripgrep", "active"), None, _ctx())
    assert len(changes) == 1
    assert changes[0].kind == "install"
    assert changes[0].action == {"op": "install", "formula": "ripgrep"}


def test_plan_retired_but_present_proposes_uninstall():
    changes = ADAPTER.plan(
        _entry("pkg-brew/ripgrep", "retired"), _obs("ripgrep", "14.1.0"), _ctx()
    )
    assert len(changes) == 1
    assert changes[0].kind == "remove"
    assert changes[0].action == {"op": "uninstall", "formula": "ripgrep"}


def test_plan_conformant_states_propose_nothing():
    ctx = _ctx()
    assert (
        ADAPTER.plan(_entry("pkg-brew/ripgrep", "active"), _obs("ripgrep"), ctx) == []
    )
    assert ADAPTER.plan(_entry("pkg-brew/ripgrep", "retired"), None, ctx) == []


# ---- execute -------------------------------------------------------------


def test_execute_install_calls_brew():
    rec = RecordingRun(code=0)
    change = Change(
        "pkg-brew/ripgrep", "install", "d", {"op": "install", "formula": "ripgrep"}
    )
    res = PkgBrewAdapter(run=rec).execute(change, _ctx())
    assert res.ok
    assert rec.calls == [["brew", "install", "ripgrep"]]
    # A confirmed install may compile for many minutes: no ceiling. The human
    # just said yes and owns the wait; a timeout here would leave torn state.
    assert rec.timeouts == [None]


def test_execute_uninstall_calls_brew():
    rec = RecordingRun(code=0)
    change = Change(
        "pkg-brew/ripgrep", "remove", "d", {"op": "uninstall", "formula": "ripgrep"}
    )
    res = PkgBrewAdapter(run=rec).execute(change, _ctx())
    assert res.ok
    assert rec.calls == [["brew", "uninstall", "ripgrep"]]


def test_execute_failure_is_reported():
    rec = RecordingRun(code=1, err="No available formula")
    change = Change(
        "pkg-brew/nope", "install", "d", {"op": "install", "formula": "nope"}
    )
    res = PkgBrewAdapter(run=rec).execute(change, _ctx())
    assert not res.ok and "failed" in res.detail


def test_execute_unknown_op_is_reported():
    res = PkgBrewAdapter(run=RecordingRun()).execute(
        Change("pkg-brew/x", "install", "d", {"op": "bogus", "formula": "x"}), _ctx()
    )
    assert not res.ok
