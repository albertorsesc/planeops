from datetime import datetime

from engine._run import RunResult
from engine.adapters.pkg_uv import ADAPTER, PkgUvAdapter, parse_uv_tools
from engine.core.contracts import Change, Ctx, Observed, can_apply
from engine.core.schema import entry_from_dict

# Illustrative `uv tool list` output. Each tool is `name vX.Y.Z`; the indented
# `- executable` lines under it are not tools.
UV_TOOL_LIST = "ruff v0.14.0\n- ruff\nmypy v1.18.0\n- mypy\n"


def _run_ok(cmd):
    return RunResult(0, UV_TOOL_LIST, "")


class RecordingRun:
    def __init__(self, code=0, err=""):
        self.calls = []
        self.code = code
        self.err = err

    def __call__(self, cmd):
        self.calls.append(cmd)
        return RunResult(self.code, "", self.err)


def _ctx():
    return Ctx(platform=None, host="testhost", now=datetime(2026, 7, 27))


def _entry(entry_id, lifecycle):
    return entry_from_dict(
        {
            "id": entry_id,
            "adapter": "pkg-uv",
            "domain": "package",
            "lifecycle": lifecycle,
            "intent": "i",
        }
    )


def _obs(name, version="1.0.0"):
    return Observed("pkg-uv", name, {}, version=version)


def test_parse_uv_tools_reads_name_and_version_skips_executables():
    tools = parse_uv_tools(UV_TOOL_LIST)
    assert tools == {"ruff": "0.14.0", "mypy": "1.18.0"}


def test_observe_reports_tools_with_versions():
    out = {o.native_id: o for o in PkgUvAdapter(run=_run_ok).observe(_ctx())}
    assert out["mypy"].version == "1.18.0"
    assert out["ruff"].key == "pkg-uv/ruff"


def test_observe_degrades_when_uv_absent():
    assert PkgUvAdapter(run=lambda c: RunResult(127, "", "no uv")).observe(_ctx()) == []


def test_pkg_uv_is_a_mutating_adapter():
    assert can_apply(ADAPTER)


def test_plan_active_but_absent_proposes_install():
    changes = ADAPTER.plan(_entry("pkg-uv/httpie", "active"), None)
    assert changes[0].kind == "install"
    assert changes[0].action == {"op": "install", "tool": "httpie"}


def test_plan_retired_but_present_proposes_uninstall():
    changes = ADAPTER.plan(_entry("pkg-uv/httpie", "retired"), _obs("httpie"))
    assert changes[0].kind == "remove"
    assert changes[0].action == {"op": "uninstall", "tool": "httpie"}


def test_plan_conformant_states_propose_nothing():
    assert ADAPTER.plan(_entry("pkg-uv/httpie", "active"), _obs("httpie")) == []
    assert ADAPTER.plan(_entry("pkg-uv/httpie", "retired"), None) == []


def test_execute_install_calls_uv():
    rec = RecordingRun(code=0)
    change = Change(
        "pkg-uv/httpie", "install", "d", {"op": "install", "tool": "httpie"}
    )
    res = PkgUvAdapter(run=rec).execute(change, _ctx())
    assert res.ok
    assert rec.calls == [["uv", "tool", "install", "httpie"]]


def test_execute_uninstall_calls_uv():
    rec = RecordingRun(code=0)
    change = Change(
        "pkg-uv/httpie", "remove", "d", {"op": "uninstall", "tool": "httpie"}
    )
    res = PkgUvAdapter(run=rec).execute(change, _ctx())
    assert res.ok
    assert rec.calls == [["uv", "tool", "uninstall", "httpie"]]


def test_execute_failure_and_unknown_op():
    rec = RecordingRun(code=1, err="No such tool")
    bad = Change("pkg-uv/x", "install", "d", {"op": "install", "tool": "x"})
    assert not PkgUvAdapter(run=rec).execute(bad, _ctx()).ok
    unknown = Change("pkg-uv/x", "install", "d", {"op": "bogus", "tool": "x"})
    assert not PkgUvAdapter(run=RecordingRun()).execute(unknown, _ctx()).ok
