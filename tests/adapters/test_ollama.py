from datetime import datetime

from engine.adapters._run import RunResult
from engine.adapters.ollama import ADAPTER, OllamaAdapter, parse_ollama_list
from engine.core.contracts import Change, Ctx, Observed, can_apply
from engine.core.schema import entry_from_dict

# Recorded from `ollama list`, trimmed. Columns are whitespace-aligned; SIZE is
# two tokens ("18 GB") and MODIFIED is fuzzy ("3 months ago").
OLLAMA_LIST = (
    "NAME                        ID              SIZE      MODIFIED     \n"
    "qwen3:30b                   ad815644918f    18 GB     3 months ago    \n"
    "llama3.2:3b                 a80c4f17acd5    2.0 GB    3 months ago    \n"
    "qwen3-embedding:0.6b        ac6da0dfba84    639 MB    2 months ago    \n"
)


def _run_ok(cmd):
    return RunResult(0, OLLAMA_LIST, "")


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
            "adapter": "ollama",
            "domain": "model",
            "lifecycle": lifecycle,
            "intent": "i",
        }
    )


def _obs(name, model_id="deadbeef1234"):
    return Observed("ollama", name, {"size": "1.0 GB"}, version=model_id)


# ---- parse / observe -----------------------------------------------------


def test_parse_ollama_list_skips_header_and_reads_id_and_size():
    models = parse_ollama_list(OLLAMA_LIST)
    assert models["qwen3:30b"] == {"id": "ad815644918f", "size": "18 GB"}
    assert models["qwen3-embedding:0.6b"]["size"] == "639 MB"
    assert "NAME" not in models


def test_observe_reports_models_with_id_as_version():
    out = {o.native_id: o for o in OllamaAdapter(run=_run_ok).observe(_ctx())}
    assert out["qwen3:30b"].version == "ad815644918f"
    assert out["qwen3:30b"].facts["size"] == "18 GB"
    assert out["llama3.2:3b"].key == "ollama/llama3.2:3b"


def test_observe_degrades_when_ollama_absent():
    def fail(cmd):
        return RunResult(127, "", "command not found: ollama")

    assert OllamaAdapter(run=fail).observe(_ctx()) == []


# ---- plan ----------------------------------------------------------------


def test_ollama_is_a_mutating_adapter():
    assert can_apply(ADAPTER)


def test_plan_active_but_absent_proposes_pull():
    changes = ADAPTER.plan(_entry("ollama/qwen3:30b", "active"), None)
    assert len(changes) == 1
    assert changes[0].kind == "install"
    assert changes[0].action == {"op": "pull", "model": "qwen3:30b"}


def test_plan_retired_but_present_proposes_remove():
    changes = ADAPTER.plan(_entry("ollama/qwen3:30b", "retired"), _obs("qwen3:30b"))
    assert len(changes) == 1
    assert changes[0].kind == "remove"
    assert changes[0].action == {"op": "remove", "model": "qwen3:30b"}


def test_plan_conformant_states_propose_nothing():
    assert ADAPTER.plan(_entry("ollama/qwen3:30b", "active"), _obs("qwen3:30b")) == []
    assert ADAPTER.plan(_entry("ollama/qwen3:30b", "retired"), None) == []


# ---- execute -------------------------------------------------------------


def test_execute_pull_calls_ollama():
    rec = RecordingRun(code=0)
    change = Change(
        "ollama/qwen3:30b", "install", "d", {"op": "pull", "model": "qwen3:30b"}
    )
    res = OllamaAdapter(run=rec).execute(change, _ctx())
    assert res.ok
    assert rec.calls == [["ollama", "pull", "qwen3:30b"]]


def test_execute_remove_calls_ollama_rm():
    rec = RecordingRun(code=0)
    change = Change(
        "ollama/qwen3:30b", "remove", "d", {"op": "remove", "model": "qwen3:30b"}
    )
    res = OllamaAdapter(run=rec).execute(change, _ctx())
    assert res.ok
    assert rec.calls == [["ollama", "rm", "qwen3:30b"]]


def test_execute_failure_is_reported():
    rec = RecordingRun(code=1, err="pull model manifest: file does not exist")
    change = Change("ollama/nope", "install", "d", {"op": "pull", "model": "nope"})
    res = OllamaAdapter(run=rec).execute(change, _ctx())
    assert not res.ok and "failed" in res.detail


def test_execute_unknown_op_is_reported():
    res = OllamaAdapter(run=RecordingRun()).execute(
        Change("ollama/x", "install", "d", {"op": "bogus", "model": "x"}), _ctx()
    )
    assert not res.ok
