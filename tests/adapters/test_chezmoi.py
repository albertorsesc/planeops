from datetime import datetime

from engine._run import RunResult
from engine.adapters.chezmoi import (
    ADAPTER,
    ChezmoiAdapter,
    parse_chezmoi_managed,
    parse_chezmoi_status,
)
from engine.core.contracts import Change, Ctx, Observed, can_apply
from engine.core.schema import entry_from_dict

MANAGED = ".zshrc\n.config/nvim/init.lua\n.gitconfig\n"
# `chezmoi status` mimics git status: `XY path`; a non-space second column means
# `chezmoi apply` would change the file. Here .zshrc and the nvim config drifted.
STATUS = " M .zshrc\n A .config/nvim/init.lua\n"


def _run_ok(cmd):
    if cmd == ["chezmoi", "managed"]:
        return RunResult(0, MANAGED, "")
    if cmd == ["chezmoi", "status"]:
        return RunResult(0, STATUS, "")
    return RunResult(1, "", "unexpected command")


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
            "adapter": "chezmoi",
            "domain": "config",
            "lifecycle": lifecycle,
            "intent": "i",
        }
    )


def _obs(name, drifted):
    return Observed("chezmoi", name, {"drifted": drifted})


# ---- parse ---------------------------------------------------------------


def test_parse_managed_lists_target_paths():
    assert parse_chezmoi_managed(MANAGED) == [
        ".zshrc",
        ".config/nvim/init.lua",
        ".gitconfig",
    ]


def test_parse_status_reads_drift_from_second_column():
    assert parse_chezmoi_status(STATUS) == {".zshrc", ".config/nvim/init.lua"}


# ---- observe -------------------------------------------------------------


def test_observe_flags_drifted_managed_files():
    out = {o.native_id: o for o in ChezmoiAdapter(run=_run_ok).observe(_ctx())}
    assert set(out) == {".zshrc", ".config/nvim/init.lua", ".gitconfig"}
    assert out[".zshrc"].facts["drifted"] is True
    assert out[".gitconfig"].facts["drifted"] is False
    assert out[".zshrc"].key == "chezmoi/.zshrc"


def test_observe_degrades_when_chezmoi_absent():
    absent = ChezmoiAdapter(run=lambda c: RunResult(127, "", "no chezmoi"))
    assert absent.observe(_ctx()) == []


# ---- plan ----------------------------------------------------------------


def test_chezmoi_is_a_mutating_adapter():
    assert can_apply(ADAPTER)


def test_plan_drifted_proposes_apply():
    changes = ADAPTER.plan(_entry("chezmoi/.zshrc", "active"), _obs(".zshrc", True))
    assert len(changes) == 1 and changes[0].kind == "configure"
    assert changes[0].action == {"op": "apply", "path": ".zshrc"}


def test_plan_clean_or_absent_proposes_nothing():
    assert ADAPTER.plan(_entry("chezmoi/.zshrc", "active"), _obs(".zshrc", False)) == []
    assert ADAPTER.plan(_entry("chezmoi/.zshrc", "active"), None) == []
    assert ADAPTER.plan(_entry("chezmoi/.zshrc", "retired"), _obs(".zshrc", True)) == []


# ---- execute -------------------------------------------------------------


def test_execute_apply_calls_chezmoi():
    rec = RecordingRun(code=0)
    change = Change(
        "chezmoi/.zshrc", "configure", "d", {"op": "apply", "path": ".zshrc"}
    )
    res = ChezmoiAdapter(run=rec).execute(change, _ctx())
    assert res.ok
    assert rec.calls == [["chezmoi", "apply", ".zshrc"]]


def test_execute_failure_and_unknown_op():
    rec = RecordingRun(code=1, err="apply failed")
    bad = Change("chezmoi/x", "configure", "d", {"op": "apply", "path": "x"})
    assert not ChezmoiAdapter(run=rec).execute(bad, _ctx()).ok
    unknown = Change("chezmoi/x", "configure", "d", {"op": "bogus", "path": "x"})
    assert not ChezmoiAdapter(run=RecordingRun()).execute(unknown, _ctx()).ok
