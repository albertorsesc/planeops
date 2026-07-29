import json

from engine.core.contracts import Observed
from engine.core.drift import triage
from engine.core.report import drift_report_dict, render_drift_json
from engine.core.schema import entry_from_dict


def _entry(**over):
    base = {
        "id": "manual/x",
        "adapter": "manual",
        "domain": "host",
        "lifecycle": "active",
        "intent": "i",
    }
    base.update(over)
    return entry_from_dict(base)


def _obs(key, **facts):
    adapter, native = key.split("/", 1)
    return Observed(adapter, native, facts)


IMPL = {"manual"}


def test_active_and_present_is_conformant():
    e = _entry()
    rep = triage([e], {"manual/x": _obs("manual/x", stale=False)}, IMPL)
    assert not rep.alerts and not rep.report and not rep.uncovered


def test_active_but_absent_is_alert():
    e = _entry()
    rep = triage([e], {}, IMPL)
    assert len(rep.alerts) == 1
    assert "not observed" in rep.alerts[0].message


def test_retired_but_present_is_alert():
    e = _entry(lifecycle="retired")
    rep = triage([e], {"manual/x": _obs("manual/x")}, IMPL)
    assert len(rep.alerts) == 1
    assert "retired" in rep.alerts[0].message


def test_retired_and_absent_is_silent():
    e = _entry(lifecycle="retired")
    rep = triage([e], {}, IMPL)
    assert not rep.alerts and not rep.report


def test_stale_attestation_is_report_not_alert():
    e = _entry()
    rep = triage([e], {"manual/x": _obs("manual/x", stale=True)}, IMPL)
    assert not rep.alerts and len(rep.report) == 1


def test_unimplemented_adapter_is_uncovered_not_alert():
    e = _entry(id="launchd/svc", adapter="launchd")
    rep = triage([e], {}, IMPL)
    assert not rep.alerts and len(rep.uncovered) == 1
    assert "launchd" in rep.uncovered[0].message


def test_interactive_auth_lists_reauth():
    e = _entry(auth="interactive")
    rep = triage([e], {"manual/x": _obs("manual/x")}, IMPL)
    assert len(rep.reauth) == 1


def test_reauth_listed_even_when_adapter_uncovered():
    e = _entry(id="claude-code/harness", adapter="claude-code", auth="interactive")
    rep = triage([e], {}, IMPL)
    assert len(rep.uncovered) == 1
    assert [i.entry_id for i in rep.reauth] == ["claude-code/harness"]


def test_parked_absent_is_report():
    e = _entry(lifecycle="parked")
    rep = triage([e], {}, IMPL)
    assert not rep.alerts and len(rep.report) == 1


def test_alert_count_property():
    entries = [_entry(id="manual/a"), _entry(id="manual/b")]
    rep = triage(entries, {}, IMPL)
    assert rep.alert_count == 2


# ---- tolerance routes the soft signals (staleness, in-major version drift) ----


def test_version_drift_folds_when_tolerance_auto():
    e = _entry(pin="1.2.3", tolerance="auto")
    obs = Observed("manual", "x", {}, version="1.2.5")
    rep = triage([e], {"manual/x": obs}, IMPL)
    assert not rep.alerts and not rep.report and len(rep.auto_folded) == 1


def test_version_drift_reports_when_tolerance_report_default():
    e = _entry(pin="1.2.3")  # tolerance defaults to report
    obs = Observed("manual", "x", {}, version="1.2.5")
    rep = triage([e], {"manual/x": obs}, IMPL)
    assert not rep.alerts and not rep.auto_folded and len(rep.report) == 1


def test_version_drift_alerts_when_tolerance_alert():
    e = _entry(pin="1.2.3", tolerance="alert")
    obs = Observed("manual", "x", {}, version="1.2.5")
    rep = triage([e], {"manual/x": obs}, IMPL)
    assert len(rep.alerts) == 1


def test_staleness_escalates_to_alert_when_tolerance_alert():
    e = _entry(tolerance="alert")
    rep = triage([e], {"manual/x": _obs("manual/x", stale=True)}, IMPL)
    assert len(rep.alerts) == 1 and not rep.report


def test_lifecycle_violation_stays_alert_even_when_tolerance_auto():
    # tolerance must never silence a structural violation
    e = _entry(tolerance="auto")
    rep = triage([e], {}, IMPL)  # active but absent
    assert len(rep.alerts) == 1 and not rep.auto_folded


def test_content_drift_fact_is_reported():
    # any adapter (e.g. chezmoi) can set facts["drifted"] to signal content drift
    e = _entry()  # default tolerance report
    rep = triage([e], {"manual/x": _obs("manual/x", drifted=True)}, IMPL)
    assert not rep.alerts and len(rep.report) == 1
    assert "drifted" in rep.report[0].message


def test_unconfigured_secret_is_alert():
    e = _entry(id="secrets/key", adapter="secrets", domain="secret")
    rep = triage(
        [e], {"secrets/key": _obs("secrets/key", configured=False)}, {"secrets"}
    )
    assert len(rep.alerts) == 1 and "secret" in rep.alerts[0].message


# ---- structured JSON pane (feeds the drift notification + the MCP surface) ----


def test_drift_report_dict_has_documented_shape():
    rep = triage([_entry()], {}, IMPL)  # active but absent -> one alert
    rep.host, rep.ts = "h", "2026-07-28T00:00:00"
    d = drift_report_dict(rep)
    assert set(d) == {
        "schema_version", "host", "ts", "alert_count", "exit_code",
        "summary", "sections",
    }  # fmt: skip
    assert d["host"] == "h" and d["ts"] == "2026-07-28T00:00:00"
    assert set(d["sections"]) == {
        "alerts", "report", "auto_folded", "uncovered", "reauth",
    }  # fmt: skip
    assert set(d["sections"]["alerts"][0]) == {"entry_id", "lifecycle", "message"}
    assert d["sections"]["alerts"][0]["entry_id"] == "manual/x"


def test_drift_report_dict_exit_code_tracks_alerts():
    absent = triage([_entry()], {}, IMPL)  # active + absent -> alert
    assert drift_report_dict(absent)["alert_count"] == 1
    assert drift_report_dict(absent)["exit_code"] == 2

    silent = triage([_entry(lifecycle="retired")], {}, IMPL)  # retired + absent
    assert drift_report_dict(silent)["alert_count"] == 0
    assert drift_report_dict(silent)["exit_code"] == 0


def test_drift_report_dict_items_sorted_by_entry_id():
    entries = [_entry(id="manual/c"), _entry(id="manual/a"), _entry(id="manual/b")]
    rep = triage(entries, {}, IMPL)  # all active + absent -> alerts
    ids = [i["entry_id"] for i in drift_report_dict(rep)["sections"]["alerts"]]
    assert ids == ["manual/a", "manual/b", "manual/c"]


def test_summary_counts_match_sections():
    entries = [_entry(id="manual/a"), _entry(id="launchd/svc", adapter="launchd")]
    rep = triage(entries, {}, IMPL)  # 1 alert + 1 uncovered
    d = drift_report_dict(rep)
    assert d["summary"] == {k: len(v) for k, v in d["sections"].items()}
    assert d["summary"]["alerts"] == 1 and d["summary"]["uncovered"] == 1


def test_render_drift_json_round_trips_to_the_dict():
    rep = triage([_entry()], {}, IMPL)
    assert json.loads(render_drift_json(rep)) == drift_report_dict(rep)
