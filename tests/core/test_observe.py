"""Integration: observe -> snapshot -> drift over a temp instance repo.

Dependencies are injected (a fake platform rooted at tmp_path, a controlled
adapter set), so nothing here touches the live machine.
"""

import json
from datetime import datetime

from engine.adapters.manual import ADAPTER as MANUAL
from engine.core.drift import run_drift
from engine.core.observe import run_observe, snapshot_path

REGISTRY = (
    "entries:\n"
    "  - {id: manual/inv, adapter: manual, domain: host, lifecycle: active, intent: i}\n"
    "  - {id: manual/key, adapter: manual, domain: secret, lifecycle: active, auth: interactive, intent: i}\n"
    "  - {id: launchd/svc, adapter: launchd, domain: service, lifecycle: active, intent: i}\n"
)

ADAPTERS = {"manual": MANUAL}
IMPLEMENTED = {"manual"}


def _seed(tmp_path):
    reg = tmp_path / "registry"
    reg.mkdir()
    (reg / "machine.yaml").write_text(REGISTRY)


def test_observe_writes_snapshot_with_uncovered(tmp_path, fake_platform):
    _seed(tmp_path)
    plat = fake_platform(tmp_path)
    now = datetime(2026, 7, 22, 12, 0, 0)
    snap = run_observe(tmp_path, attest=True, now=now, platform=plat, adapters=ADAPTERS)

    assert snap["host"] == "testhost"
    assert snap["engine_version"]
    assert snap["uncovered"] == ["launchd"]

    keys = {o["adapter"] + "/" + o["native_id"] for o in snap["observed"]}
    assert keys == {"manual/inv", "manual/key"}

    on_disk = json.loads(snapshot_path(tmp_path / "observed", "testhost").read_text())
    assert on_disk == snap


def test_second_observe_reuses_attestation_no_alerts(tmp_path, fake_platform):
    _seed(tmp_path)
    plat = fake_platform(tmp_path)
    run_observe(
        tmp_path,
        attest=True,
        now=datetime(2026, 7, 22, 12, 0, 0),
        platform=plat,
        adapters=ADAPTERS,
    )
    # A later run without --attest reuses the prior attestation, still fresh.
    run_observe(
        tmp_path, now=datetime(2026, 7, 25, 5, 0, 0), platform=plat, adapters=ADAPTERS
    )
    report = run_drift(
        tmp_path,
        now=datetime(2026, 7, 25, 5, 0, 0),
        platform=plat,
        implemented=IMPLEMENTED,
    )
    assert report.alert_count == 0


def test_drift_triage_over_seed(tmp_path, fake_platform):
    _seed(tmp_path)
    plat = fake_platform(tmp_path)
    now = datetime(2026, 7, 22, 12, 0, 0)
    run_observe(tmp_path, attest=True, now=now, platform=plat, adapters=ADAPTERS)
    report = run_drift(tmp_path, now=now, platform=plat, implemented=IMPLEMENTED)

    assert report.alert_count == 0
    assert [i.entry_id for i in report.uncovered] == ["launchd/svc"]
    assert [i.entry_id for i in report.reauth] == ["manual/key"]
    assert (tmp_path / "observed" / report.host / "DRIFT.md").is_file()


def test_drift_writes_machine_readable_json_pane(tmp_path, fake_platform):
    _seed(tmp_path)
    plat = fake_platform(tmp_path)
    now = datetime(2026, 7, 22, 12, 0, 0)
    run_observe(tmp_path, attest=True, now=now, platform=plat, adapters=ADAPTERS)
    report = run_drift(tmp_path, now=now, platform=plat, implemented=IMPLEMENTED)

    drift_json = tmp_path / "observed" / report.host / "DRIFT.json"
    assert drift_json.is_file()  # written alongside DRIFT.md, no flag needed
    data = json.loads(drift_json.read_text())
    assert data["host"] == report.host
    assert data["ts"] == now.isoformat()
    assert data["exit_code"] == (2 if report.alert_count else 0)
    assert [i["entry_id"] for i in data["sections"]["uncovered"]] == ["launchd/svc"]
    assert [i["entry_id"] for i in data["sections"]["reauth"]] == ["manual/key"]


def test_drift_without_snapshot_errors(tmp_path, fake_platform):
    _seed(tmp_path)
    plat = fake_platform(tmp_path)
    try:
        run_drift(tmp_path, platform=plat, implemented=IMPLEMENTED)
    except FileNotFoundError as exc:
        assert "plane observe" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


class RaisingAdapter:
    name = "boom"
    domains: tuple[str, ...] = ()

    def observe(self, ctx):
        raise RuntimeError("kaboom")


def test_one_failing_adapter_degrades_not_crashes(tmp_path, fake_platform):
    _seed(tmp_path)
    plat = fake_platform(tmp_path)
    now = datetime(2026, 7, 22, 12, 0, 0)
    adapters = {"manual": MANUAL, "boom": RaisingAdapter()}
    snap = run_observe(tmp_path, attest=True, now=now, platform=plat, adapters=adapters)
    # manual is still observed; the crashing adapter is recorded, not fatal
    keys = {o["adapter"] + "/" + o["native_id"] for o in snap["observed"]}
    assert keys == {"manual/inv", "manual/key"}
    assert snap["failed"] == [{"adapter": "boom", "error": "kaboom"}]
    assert snap["schema_version"] == 1


def test_observe_survives_a_torn_prior_snapshot(tmp_path, fake_platform):
    # A snapshot corrupted mid-write must not crash the next observe: the prior reads
    # as empty and observe re-establishes it. (Regression: unguarded _load_prior.)
    _seed(tmp_path)
    snap_dir = tmp_path / "observed" / "testhost"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.json").write_text("{half-written")  # torn
    now = datetime(2026, 7, 29, 12, 0, 0)
    snap = run_observe(
        tmp_path,
        attest=True,
        now=now,
        platform=fake_platform(tmp_path),
        adapters=ADAPTERS,
    )
    assert snap["host"] == "testhost"  # did not raise


def test_observe_writes_the_snapshot_atomically(tmp_path, fake_platform):
    # No temp sibling is left behind: the write is temp+rename, not in-place.
    _seed(tmp_path)
    now = datetime(2026, 7, 29, 12, 0, 0)
    run_observe(
        tmp_path,
        attest=True,
        now=now,
        platform=fake_platform(tmp_path),
        adapters=ADAPTERS,
    )
    assert not (tmp_path / "observed" / "testhost" / "snapshot.json.tmp").exists()
