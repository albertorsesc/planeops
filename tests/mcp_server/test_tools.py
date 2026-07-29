"""The logic behind the MCP tools, with no `mcp` dependency, so it always runs in
the gate. Exercised over a temp repo with a fake platform: nothing real is touched,
and the tools are proven to be a thin pass-through to the engine (drift returns the
same structure `plane drift --json` emits).
"""

from datetime import datetime

from engine.adapters.manual import ADAPTER as MANUAL
from engine.mcp_server.tools import drift_state, observe_state

REGISTRY = (
    "entries:\n"
    "  - {id: manual/inv, adapter: manual, domain: host, lifecycle: active, intent: i}\n"
    "  - {id: launchd/svc, adapter: launchd, domain: service, lifecycle: active, intent: i}\n"
)
ADAPTERS = {"manual": MANUAL}
IMPLEMENTED = {"manual"}


def _seed(tmp_path):
    reg = tmp_path / "registry"
    reg.mkdir()
    (reg / "machine.yaml").write_text(REGISTRY)


def test_observe_state_returns_only_aggregate_counts(tmp_path, fake_platform):
    _seed(tmp_path)
    now = datetime(2026, 7, 28, 12, 0, 0)
    out = observe_state(
        tmp_path, now=now, platform=fake_platform(tmp_path), adapters=ADAPTERS
    )
    # Exact shape: only aggregates cross the boundary, never raw observed facts. If a
    # regression leaks `facts`/`observed`, this fails (the one security invariant).
    assert set(out) == {
        "host", "ts", "observed_count", "by_adapter", "uncovered", "failed",
    }  # fmt: skip
    assert out["host"] == "testhost"
    assert out["ts"] == now.isoformat()
    assert out["uncovered"] == ["launchd"]  # declared, but no adapter was provided
    assert isinstance(out["by_adapter"], dict)


def test_drift_state_reads_last_snapshot_and_writes_nothing(tmp_path, fake_platform):
    _seed(tmp_path)
    plat = fake_platform(tmp_path)
    now = datetime(2026, 7, 28, 12, 0, 0)
    observe_state(
        tmp_path, now=now, platform=plat, adapters=ADAPTERS
    )  # writes snapshot
    out = drift_state(tmp_path, now=now, platform=plat, implemented=IMPLEMENTED)

    assert set(out) == {
        "schema_version", "host", "ts", "alert_count", "exit_code",
        "summary", "sections",
    }  # fmt: skip
    assert out["host"] == "testhost"
    assert [i["entry_id"] for i in out["sections"]["uncovered"]] == ["launchd/svc"]
    # Pure read: the drift tool writes no DRIFT panes (only observe/apply write).
    out_dir = tmp_path / "observed" / "testhost"
    assert not (out_dir / "DRIFT.md").exists()
    assert not (out_dir / "DRIFT.json").exists()


def test_drift_state_without_snapshot_returns_structured_error(tmp_path, fake_platform):
    _seed(tmp_path)  # no observe run, so no snapshot exists
    out = drift_state(
        tmp_path, platform=fake_platform(tmp_path), implemented=IMPLEMENTED
    )
    assert set(out) == {"error"}
    assert "snapshot" in out["error"]  # tells the caller to observe first
