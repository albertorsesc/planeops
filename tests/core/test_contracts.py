from datetime import datetime

from planeops.core.contracts import Adapter, Ctx, Observed


class ObserveOnly:
    name = "o"
    domains = ()

    def observe(self, ctx):
        return []


def test_observe_only_class_satisfies_adapter():
    assert isinstance(ObserveOnly(), Adapter)


def test_non_adapter_is_rejected():
    class Missing:
        name = "x"

    assert not isinstance(Missing(), Adapter)


def test_observed_key_matches_entry_id_convention():
    assert Observed("launchd", "ai.x", {}).key == "launchd/ai.x"


def test_observed_roundtrips_through_dict():
    o = Observed("ollama", "llama3.2:3b", {"loaded": True}, version="1")
    assert Observed.from_dict(o.to_dict()) == o


def test_ctx_defaults_are_empty():
    ctx = Ctx(platform=object(), host="h", now=datetime(2026, 7, 22))
    assert ctx.entries == () and ctx.prior == {} and ctx.attest is False
