"""`read_status`: a pure read of the last DRIFT.json, no recompute, no machine scan."""

import json

from engine.core.status import read_status


def _write_drift(tmp_path, host, data):
    d = tmp_path / "observed" / host
    d.mkdir(parents=True)
    (d / "DRIFT.json").write_text(json.dumps(data))


def test_read_status_returns_the_stored_report(tmp_path, fake_platform):
    _write_drift(tmp_path, "testhost", {"alert_count": 3, "ts": "2026-07-29T00:00:00"})
    out = read_status(tmp_path, platform=fake_platform(tmp_path))
    assert out is not None
    assert out["alert_count"] == 3


def test_read_status_is_none_when_no_report_yet(tmp_path, fake_platform):
    assert read_status(tmp_path, platform=fake_platform(tmp_path)) is None


def test_read_status_does_not_write_or_scan(tmp_path, fake_platform):
    # A pure read: with no report present it returns None and creates nothing.
    read_status(tmp_path, platform=fake_platform(tmp_path))
    assert not (tmp_path / "observed").exists()


def test_read_status_returns_none_on_a_torn_or_corrupt_file(tmp_path, fake_platform):
    # A half-written DRIFT.json reads as "no report", never a crash, so `plane
    # status --short` stays prompt-safe even mid-rewrite.
    d = tmp_path / "observed" / "testhost"
    d.mkdir(parents=True)
    (d / "DRIFT.json").write_text("{partial")  # invalid / half-written JSON
    assert read_status(tmp_path, platform=fake_platform(tmp_path)) is None


def test_read_status_round_trips_a_real_drift_report(tmp_path, fake_platform):
    # Pins the producer->consumer contract: what `render_drift_json` writes is
    # exactly what `read_status` returns, including the keys `plane status` reads.
    from engine.core.drift import DriftItem, DriftReport
    from engine.core.report import drift_report_dict, render_drift_json

    rep = DriftReport(host="testhost", ts="2026-07-29T00:00:00")
    rep.alerts = [DriftItem("manual/x", "active", "expected present, not observed")]
    d = tmp_path / "observed" / "testhost"
    d.mkdir(parents=True)
    (d / "DRIFT.json").write_text(render_drift_json(rep))

    out = read_status(tmp_path, platform=fake_platform(tmp_path))
    assert out == drift_report_dict(rep)
    assert out["alert_count"] == 1  # keys `_cmd_status` depends on
    assert {"report", "uncovered"} <= set(out["summary"])


def test_read_status_returns_none_on_valid_json_that_is_not_an_object(
    tmp_path, fake_platform
):
    # A DRIFT.json that is valid JSON but a list/scalar (hand-edited, foreign schema)
    # reads as "no report", never an AttributeError on the consumer side.
    d = tmp_path / "observed" / "testhost"
    d.mkdir(parents=True)
    (d / "DRIFT.json").write_text("[]")
    assert read_status(tmp_path, platform=fake_platform(tmp_path)) is None
