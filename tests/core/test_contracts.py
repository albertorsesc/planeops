import inspect
from datetime import datetime
from typing import get_type_hints

import pytest

from planeops.core.contracts import Adapter, Ctx, Observed
from planeops.core.facts import GENERAL


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


# `Observed.of` is how an adapter states the facts the triage reads. Naming
# them as arguments is what makes a misspelling an error a type checker can
# see, at the line that wrote it, rather than a fact nobody reads.


def test_of_puts_the_general_facts_in_the_facts_map():
    o = Observed.of("launchd", "ai.x", present=True, always_on=False)
    assert o.facts == {"present": True, "always_on": False}
    assert o.key == "launchd/ai.x"


def test_of_carries_domain_facts_through_detail():
    o = Observed.of("mcp", "srv", detail={"command": "npx", "wirings": []})
    assert o.facts == {"command": "npx", "wirings": []}


def test_of_keeps_the_general_facts_alongside_the_domain_ones():
    o = Observed.of("footprint", "gh", present=True, detail={"footprints": ["~/x"]})
    assert o.facts == {"present": True, "footprints": ["~/x"]}


def test_an_omitted_general_fact_is_absent_rather_than_none():
    # The triage reads a missing fact as "this domain does not say", which is
    # not the same as saying no, so an unset argument must leave no key.
    o = Observed.of("pkg-brew", "gh", version="2.0")
    assert o.facts == {}
    assert o.version == "2.0"


def test_a_general_fact_that_is_false_is_recorded():
    # The distinction the above rests on: False is a statement, None is silence.
    o = Observed.of("launchd", "ai.x", present=False)
    assert o.facts == {"present": False}


def test_detail_may_not_carry_a_general_fact():
    # Routing them around the named arguments would put back exactly the hole
    # the named arguments close.
    with pytest.raises(ValueError, match="present"):
        Observed.of("launchd", "ai.x", detail={"present": True})


def test_of_refuses_a_general_fact_of_the_wrong_type():
    with pytest.raises(ValueError, match="always_on"):
        Observed.of("launchd", "ai.x", always_on="yes")


def test_of_names_every_general_fact_and_nothing_else():
    # The vocabulary lives in `facts.GENERAL`; these arguments mirror it. Two
    # lists that must agree will drift, so the agreement is asserted.
    params = inspect.signature(Observed.of).parameters
    named = set(params) - {"adapter", "native_id", "version", "detail"}
    assert named == set(GENERAL)


def test_each_general_fact_is_annotated_with_the_type_the_triage_expects():
    hints = get_type_hints(Observed.of)
    for name, expected in GENERAL.items():
        assert hints[name] == expected | None, name
