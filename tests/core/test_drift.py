from engine.core.contracts import Observed
from engine.core.drift import triage
from engine.core.schema import entry_from_dict


def _entry(**over):
    base = {"id": "manual/x", "adapter": "manual", "domain": "host", "lifecycle": "active", "intent": "i"}
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
