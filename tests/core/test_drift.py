import json

import pytest

from planeops.core.contracts import Observed
from planeops.core.drift import triage
from planeops.core.report import drift_report_dict, render_drift_json
from planeops.core.schema import entry_from_dict


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


def test_retired_and_absent_reports_completion():
    # The entry was a work order; once reality converged, the closing move is
    # deleting the line, and the report says so until it happens.
    e = _entry(lifecycle="retired")
    rep = triage([e], {}, IMPL)
    assert not rep.alerts and len(rep.report) == 1
    assert "remove the entry" in rep.report[0].message


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
        "alerts", "report", "auto_folded", "uncovered", "ungoverned", "reauth",
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


# ---- needs: a consumer can't be pruned out from under (dependency integrity) ----


def test_needs_a_retired_dependency_alerts_the_consumer():
    # The protective case: mark the embedding `retired` and the tool that needs it
    # alerts BEFORE you ever apply the removal.
    consumer = _entry(id="mcp/gitnexus", adapter="mcp", needs=["ollama/emb"])
    dep = _entry(id="ollama/emb", adapter="ollama", lifecycle="retired")
    obs = {"mcp/gitnexus": _obs("mcp/gitnexus"), "ollama/emb": _obs("ollama/emb")}
    rep = triage([consumer, dep], obs, {"mcp", "ollama"})
    consumer_alerts = [a for a in rep.alerts if a.entry_id == "mcp/gitnexus"]
    assert len(consumer_alerts) == 1
    assert "needs ollama/emb" in consumer_alerts[0].message
    assert "retired" in consumer_alerts[0].message


def test_needs_an_absent_dependency_alerts_the_consumer():
    consumer = _entry(id="mcp/gitnexus", adapter="mcp", needs=["ollama/emb"])
    rep = triage([consumer], {"mcp/gitnexus": _obs("mcp/gitnexus")}, {"mcp"})
    assert [a.entry_id for a in rep.alerts] == ["mcp/gitnexus"]
    assert "needs ollama/emb" in rep.alerts[0].message
    assert "not present" in rep.alerts[0].message


def test_needs_a_present_active_dependency_is_conformant():
    consumer = _entry(id="mcp/gitnexus", adapter="mcp", needs=["ollama/emb"])
    dep = _entry(id="ollama/emb", adapter="ollama")  # active + present
    obs = {"mcp/gitnexus": _obs("mcp/gitnexus"), "ollama/emb": _obs("ollama/emb")}
    assert not triage([consumer, dep], obs, {"mcp", "ollama"}).alerts


def test_needs_is_not_checked_for_a_non_active_consumer():
    # A consumer that isn't active isn't relying on its deps right now.
    consumer = _entry(
        id="mcp/gitnexus", adapter="mcp", lifecycle="parked", needs=["ollama/emb"]
    )
    rep = triage([consumer], {}, {"mcp"})  # emb absent, but the consumer is parked
    assert not rep.alerts  # parked+absent is a report, not an alert, and no needs-alert


def test_needs_defaults_to_empty():
    assert _entry().needs == ()


def test_needs_a_declared_but_absent_dependency_says_not_present():
    consumer = _entry(id="mcp/gitnexus", adapter="mcp", needs=["ollama/emb"])
    dep = _entry(id="ollama/emb", adapter="ollama")  # active, but not observed
    rep = triage(
        [consumer, dep], {"mcp/gitnexus": _obs("mcp/gitnexus")}, {"mcp", "ollama"}
    )
    consumer_alerts = [a for a in rep.alerts if a.entry_id == "mcp/gitnexus"]
    assert len(consumer_alerts) == 1 and "not present" in consumer_alerts[0].message


def test_needs_a_dependency_whose_adapter_is_unbuilt_does_not_false_alarm():
    # The dep's adapter isn't implemented, so presence can't be judged; the consumer
    # must NOT be told "not present" (it's uncovered, not absent).
    consumer = _entry(id="mcp/gitnexus", adapter="mcp", needs=["future/thing"])
    dep = _entry(id="future/thing", adapter="future")
    rep = triage([consumer, dep], {"mcp/gitnexus": _obs("mcp/gitnexus")}, {"mcp"})
    assert not [a for a in rep.alerts if a.entry_id == "mcp/gitnexus"]


def test_needs_is_checked_for_a_maintain_consumer():
    consumer = _entry(
        id="mcp/x", adapter="mcp", lifecycle="maintain", needs=["ollama/emb"]
    )
    dep = _entry(id="ollama/emb", adapter="ollama", lifecycle="retired")
    obs = {"mcp/x": _obs("mcp/x"), "ollama/emb": _obs("ollama/emb")}
    rep = triage([consumer, dep], obs, {"mcp", "ollama"})
    assert any(a.entry_id == "mcp/x" and "ollama/emb" in a.message for a in rep.alerts)


def test_needs_cycle_and_self_reference_terminate_without_alert():
    a = _entry(id="mcp/a", adapter="mcp", needs=["mcp/b", "mcp/a"])
    b = _entry(id="mcp/b", adapter="mcp", needs=["mcp/a"])
    obs = {"mcp/a": _obs("mcp/a"), "mcp/b": _obs("mcp/b")}
    assert not triage([a, b], obs, {"mcp"}).alerts


# ---- ungoverned observations ----


def test_ungoverned_observation_lands_in_its_section():
    # Observed on the machine, absent from the registry: surfaced, not silent.
    rep = triage([], {"manual/x": _obs("manual/x")}, IMPL)
    assert not rep.alerts
    assert [i.entry_id for i in rep.ungoverned] == ["manual/x"]


def test_ungoverned_always_on_service_alerts():
    # A self-installed always-on agent (keepalive/login/interval) runs code
    # without ever being declared; the adapter marks it always_on, drift alerts.
    rep = triage([], {"launchd/evil": _obs("launchd/evil", always_on=True)}, IMPL)
    assert len(rep.alerts) == 1
    assert "ungoverned" in rep.alerts[0].message
    assert not rep.ungoverned  # escalated, not double-listed


def test_declared_observation_is_not_ungoverned():
    e = _entry()
    rep = triage([e], {"manual/x": _obs("manual/x")}, IMPL)
    assert not rep.ungoverned


# ---- failed adapter scans (state unknown, not "absent") ----


def test_failed_adapter_scan_alerts_state_unknown_not_absent():
    # An adapter that crashed during observe produced no observations; its entries
    # must not misreport as "expected present, not observed" (a false story).
    e = _entry()
    rep = triage([e], {}, IMPL, failed={"manual": "boom"})
    assert len(rep.alerts) == 1
    assert "scan failed" in rep.alerts[0].message
    assert "not observed" not in rep.alerts[0].message


def test_json_pane_includes_ungoverned_and_bumps_schema():
    rep = triage([], {"manual/x": _obs("manual/x")}, IMPL)
    d = drift_report_dict(rep)
    assert d["schema_version"] == 2  # new section = new shape, consumers can pin
    assert [i["entry_id"] for i in d["sections"]["ungoverned"]] == ["manual/x"]
    assert d["summary"]["ungoverned"] == 1


# ---- semantic presence: retired means "not running", purge means "no file" ----


def test_retired_entry_with_semantically_absent_obs_reports_completion():
    # A booted-out service whose file remains on disk must not alert forever
    # while apply plans nothing (already unloaded). The adapter says what
    # "present" means for its domain: retired + present=False is conformant,
    # and the completed retirement asks for its entry to be removed.
    e = _entry(lifecycle="retired")
    rep = triage([e], {"manual/x": _obs("manual/x", present=False)}, IMPL)
    assert not rep.alerts and len(rep.report) == 1
    assert "remove the entry" in rep.report[0].message


def test_retired_entry_with_semantically_present_obs_still_alerts():
    e = _entry(lifecycle="retired")
    rep = triage([e], {"manual/x": _obs("manual/x", present=True)}, IMPL)
    assert len(rep.alerts) == 1


def test_retired_entry_without_a_present_fact_keeps_alerting():
    # Package-style adapters (brew/ollama/npm) declare no `present` fact because
    # observed-at-all IS presence for them; the default must stay strict.
    e = _entry(lifecycle="retired")
    rep = triage([e], {"manual/x": _obs("manual/x")}, IMPL)
    assert len(rep.alerts) == 1


def test_run_drift_on_a_corrupt_snapshot_raises_a_clean_error(tmp_path):
    # A torn/hand-mangled snapshot must say what to do, not traceback in json.
    from planeops.core.drift import run_drift

    class _Plat:
        name = "fake"

        def hostname(self):
            return "h"

        def home(self):
            return tmp_path

    (tmp_path / "registry").mkdir()
    obs = tmp_path / "observed" / "h"
    obs.mkdir(parents=True)
    (obs / "snapshot.json").write_text("{ torn mid-write")
    with pytest.raises(FileNotFoundError, match="plane observe"):
        run_drift(tmp_path, platform=_Plat())


def test_malformed_observed_items_are_skipped_not_fatal(tmp_path):
    # Snapshot items missing keys (hand-edit, schema drift) are dropped; the
    # valid remainder still triages.
    from planeops.core.drift import run_drift

    class _Plat:
        name = "fake"

        def hostname(self):
            return "h"

        def home(self):
            return tmp_path

    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "r.yaml").write_text(
        "entries:\n  - {id: manual/x, adapter: manual, domain: d, lifecycle: active, intent: i}\n"
    )
    obs = tmp_path / "observed" / "h"
    obs.mkdir(parents=True)
    (obs / "snapshot.json").write_text(
        json.dumps(
            {
                "host": "h",
                "observed": [
                    {"native_id": "orphan"},  # missing adapter: skipped
                    "not-a-dict",  # skipped
                    {"adapter": "manual", "native_id": "x", "facts": {}},
                ],
            }
        )
    )
    rep = run_drift(tmp_path, platform=_Plat(), write=False)
    assert not rep.alerts  # manual/x observed; junk items didn't poison the run


def test_reauth_clears_once_the_credential_is_configured():
    # The checklist must empty as the human works it: a configured interactive
    # credential drops off; an unconfigured or unobserved one stays.
    def secret(name):
        return entry_from_dict(
            {"id": f"secrets/{name}", "adapter": "secrets", "domain": "secret",
             "lifecycle": "active", "auth": "interactive", "intent": "i"}
        )  # fmt: skip

    done, pending, unobserved = secret("done"), secret("pending"), secret("gone")
    observed = {
        "secrets/done": _obs("secrets/done", configured=True),
        "secrets/pending": _obs("secrets/pending", configured=False),
    }
    rep = triage([done, pending, unobserved], observed, IMPL)
    assert [i.entry_id for i in rep.reauth] == ["secrets/pending", "secrets/gone"]


def _secret(name, **over):
    base = {
        "id": f"secrets/{name}",
        "adapter": "secrets",
        "domain": "secret",
        "lifecycle": "active",
        "intent": "i",
    }
    base.update(over)
    return entry_from_dict(base)


def test_parked_secret_unconfigured_is_silent():
    # Parked means deliberately dormant: unconfigured is the expected state,
    # and there is nothing to re-auth right now.
    e = _secret("dormant", lifecycle="parked", auth="interactive")
    obs = {"secrets/dormant": _obs("secrets/dormant", configured=False, present=False)}
    rep = triage([e], obs, {"secrets"})
    assert not rep.alerts and not rep.report and not rep.reauth


def test_retired_secret_unconfigured_reports_completion():
    e = _secret("gone", lifecycle="retired")
    obs = {"secrets/gone": _obs("secrets/gone", configured=False, present=False)}
    rep = triage([e], obs, {"secrets"})
    assert not rep.alerts and len(rep.report) == 1
    assert "remove the entry" in rep.report[0].message


def test_retired_secret_with_a_lingering_value_alerts():
    e = _secret("lingering", lifecycle="retired")
    obs = {
        "secrets/lingering": _obs("secrets/lingering", configured=True, present=True)
    }
    rep = triage([e], obs, {"secrets"})
    assert len(rep.alerts) == 1 and "still observed present" in rep.alerts[0].message
