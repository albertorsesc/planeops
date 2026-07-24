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
    run_observe(tmp_path, attest=True, now=datetime(2026, 7, 22, 12, 0, 0), platform=plat, adapters=ADAPTERS)
    # A later run without --attest reuses the prior attestation, still fresh.
    run_observe(tmp_path, now=datetime(2026, 7, 25, 5, 0, 0), platform=plat, adapters=ADAPTERS)
    report = run_drift(tmp_path, now=datetime(2026, 7, 25, 5, 0, 0), platform=plat, implemented=IMPLEMENTED)
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


def test_drift_without_snapshot_errors(tmp_path, fake_platform):
    _seed(tmp_path)
    plat = fake_platform(tmp_path)
    try:
        run_drift(tmp_path, platform=plat, implemented=IMPLEMENTED)
    except FileNotFoundError as exc:
        assert "plane observe" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")
