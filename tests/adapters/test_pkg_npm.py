import json
from datetime import datetime

from planeops._run import RunResult
from planeops.adapters.pkg_npm import ADAPTER, PkgNpmAdapter, parse_npm_globals
from planeops.core.contracts import Change, Ctx, Observed, can_apply
from planeops.core.schema import entry_from_dict

# Illustrative `npm ls -g --depth=0 --json` output.
NPM_GLOBAL = (
    '{"name":"lib","dependencies":{'
    '"typescript":{"version":"5.6.2","overridden":false},'
    '"prettier":{"version":"3.3.3","overridden":false},'
    '"npm":{"version":"11.11.0","overridden":false}'
    "}}"
)


def _run_ok(cmd):
    return RunResult(0, NPM_GLOBAL, "")


class RecordingRun:
    def __init__(self, code=0, err=""):
        self.calls = []
        self.code = code
        self.err = err

    def __call__(self, cmd, *, timeout=30):
        self.calls.append(cmd)
        return RunResult(self.code, "", self.err)


def _ctx():
    return Ctx(platform=_Plat(), host="testhost", now=datetime(2026, 7, 27))


class _Plat:
    """Minimal Platform stub: plan/execute receive a real ctx, per the contract."""

    name = "fake"

    def hostname(self):
        return "testhost"

    def home(self):
        from pathlib import Path

        return Path("/home/fake")


def _entry(entry_id, lifecycle):
    return entry_from_dict(
        {
            "id": entry_id,
            "adapter": "pkg-npm",
            "domain": "package",
            "lifecycle": lifecycle,
            "intent": "i",
        }
    )


def _obs(name, version="1.0.0"):
    return Observed("pkg-npm", name, {}, version=version)


def test_parse_npm_globals_reads_names_and_versions():
    assert parse_npm_globals(NPM_GLOBAL) == {
        "typescript": "5.6.2",
        "prettier": "3.3.3",
        "npm": "11.11.0",
    }


def test_parse_npm_globals_tolerates_garbage():
    assert parse_npm_globals("not json") == {}
    assert parse_npm_globals("") == {}


def test_observe_reports_packages_with_versions():
    out = {o.native_id: o for o in PkgNpmAdapter(run=_run_ok).observe(_ctx())}
    assert out["typescript"].version == "5.6.2"
    assert out["prettier"].key == "pkg-npm/prettier"


def test_observe_parses_json_even_when_npm_exits_nonzero():
    # `npm ls -g` exits 1 on dep-tree warnings while still printing valid JSON.
    out = PkgNpmAdapter(run=lambda c: RunResult(1, NPM_GLOBAL, "warn")).observe(_ctx())
    assert {o.native_id for o in out} == {"typescript", "prettier", "npm"}


def test_observe_degrades_when_npm_absent():
    assert (
        PkgNpmAdapter(run=lambda c: RunResult(127, "", "no npm")).observe(_ctx()) == []
    )


def test_pkg_npm_is_a_mutating_adapter():
    assert can_apply(ADAPTER)


def test_plan_active_but_absent_proposes_install():
    changes = ADAPTER.plan(_entry("pkg-npm/typescript", "active"), None, _ctx())
    assert changes[0].kind == "install"
    assert changes[0].action == {"op": "install", "package": "typescript"}


def test_plan_retired_but_present_proposes_uninstall():
    changes = ADAPTER.plan(
        _entry("pkg-npm/typescript", "retired"), _obs("typescript"), _ctx()
    )
    assert changes[0].kind == "remove"
    assert changes[0].action == {"op": "uninstall", "package": "typescript"}


def test_plan_conformant_states_propose_nothing():
    ctx = _ctx()
    assert (
        ADAPTER.plan(_entry("pkg-npm/typescript", "active"), _obs("typescript"), ctx)
        == []
    )
    assert ADAPTER.plan(_entry("pkg-npm/typescript", "retired"), None, ctx) == []


def test_execute_install_calls_npm():
    rec = RecordingRun(code=0)
    change = Change(
        "pkg-npm/typescript",
        "install",
        "d",
        {"op": "install", "package": "typescript"},
    )
    res = PkgNpmAdapter(run=rec).execute(change, _ctx())
    assert res.ok
    assert rec.calls == [["npm", "install", "-g", "typescript"]]


def test_execute_uninstall_calls_npm():
    rec = RecordingRun(code=0)
    change = Change(
        "pkg-npm/typescript",
        "remove",
        "d",
        {"op": "uninstall", "package": "typescript"},
    )
    res = PkgNpmAdapter(run=rec).execute(change, _ctx())
    assert res.ok
    assert rec.calls == [["npm", "uninstall", "-g", "typescript"]]


def test_execute_failure_and_unknown_op():
    rec = RecordingRun(code=1, err="404 Not Found")
    bad = Change("pkg-npm/x", "install", "d", {"op": "install", "package": "x"})
    assert not PkgNpmAdapter(run=rec).execute(bad, _ctx()).ok
    unknown = Change("pkg-npm/x", "install", "d", {"op": "bogus", "package": "x"})
    assert not PkgNpmAdapter(run=RecordingRun()).execute(unknown, _ctx()).ok


def test_versionless_globals_are_observed_not_dropped():
    # npm reports some installs without a version key (a linked or broken
    # global, e.g. a real machine's tree-sitter-dart). Dropping them made the
    # snapshot lie: the package IS installed. Observe it, version unknown.
    text = json.dumps(
        {
            "dependencies": {
                "good": {"version": "1.0.0"},
                "linked": {"overridden": False},
            }
        }
    )
    out = parse_npm_globals(text)
    assert out["good"] == "1.0.0"
    assert "linked" in out and out["linked"] is None
