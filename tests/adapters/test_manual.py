from datetime import datetime, timedelta

from engine.adapters.manual import ADAPTER
from engine.core.contracts import Ctx, Observed
from engine.core.schema import entry_from_dict


def _ctx(entries, *, prior=None, attest=False, now=None):
    return Ctx(
        platform=object(),
        host="testhost",
        now=now or datetime(2026, 7, 22, 12, 0, 0),
        entries=tuple(entries),
        prior=prior or {},
        attest=attest,
    )


def _entry(id="manual/thing", adapter="manual"):
    return entry_from_dict(
        {"id": id, "adapter": adapter, "domain": "host", "lifecycle": "active", "intent": "x"}
    )


def test_only_attests_its_own_entries():
    entries = [_entry("manual/a"), _entry("launchd/b", adapter="launchd")]
    out = ADAPTER.observe(_ctx(entries))
    assert [o.key for o in out] == ["manual/a"]


def test_attest_records_now_and_not_stale():
    now = datetime(2026, 7, 22, 12, 0, 0)
    out = ADAPTER.observe(_ctx([_entry()], attest=True, now=now))
    assert out[0].facts["attested_at"] == now.isoformat()
    assert out[0].facts["stale"] is False


def test_non_interactive_reuses_prior_attestation():
    prior_when = datetime(2026, 7, 20, 9, 0, 0).isoformat()
    prior = {"manual/thing": Observed("manual", "thing", {"attested_at": prior_when})}
    out = ADAPTER.observe(_ctx([_entry()], prior=prior))
    assert out[0].facts["attested_at"] == prior_when
    assert out[0].facts["stale"] is False


def test_attestation_goes_stale_after_30_days():
    now = datetime(2026, 7, 22, 12, 0, 0)
    old = (now - timedelta(days=31)).isoformat()
    prior = {"manual/thing": Observed("manual", "thing", {"attested_at": old})}
    out = ADAPTER.observe(_ctx([_entry()], prior=prior, now=now))
    assert out[0].facts["stale"] is True


def test_never_attested_is_stale():
    out = ADAPTER.observe(_ctx([_entry()]))
    assert out[0].facts["attested_at"] is None
    assert out[0].facts["stale"] is True


def test_manual_has_no_execute():
    assert not hasattr(ADAPTER, "execute")
