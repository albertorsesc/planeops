"""The general facts the triage understands, checked where they are produced.

`Observed.facts` is deliberately open: an adapter records whatever its domain
needs, and the engine reads the handful of names it acts on. That openness is
what makes a typo dangerous, because a fact the triage never reads is a fact
that silently does nothing, and a `present` that is a string is worse than
missing: it reads as the opposite of what it says.
"""

import pytest

from planeops.core.facts import GENERAL, check_facts


def test_the_vocabulary_is_the_one_the_spec_documents():
    assert set(GENERAL) == {
        "present", "drifted", "always_on", "stale", "configured", "governed_by",
    }  # fmt: skip


def test_an_adapter_may_record_anything_of_its_own():
    # The open part: domain facts are none of the engine's business.
    check_facts("launchd", "svc", {"pid": 42, "keepalive": True, "plist_path": "/x"})
    check_facts("mcp", "srv", {"wirings": [{"client": "a"}], "command": "npx"})
    check_facts("footprint", "gh", {"footprints": [{"path": "~/.config/gh"}]})


def test_a_general_fact_of_the_right_type_passes():
    check_facts("launchd", "svc", {"present": True, "always_on": False})
    check_facts("footprint", "gh", {"governed_by": "pkg-brew/gh"})


@pytest.mark.parametrize(
    "typo", ["alwayson", "always-on", "Present", "presnt", "governedby", "stale_"]
)
def test_a_near_miss_of_a_general_fact_is_refused(typo):
    # This is the whole point: a name the triage will never read, close enough
    # to one it would, means the adapter author meant the real one.
    with pytest.raises(ValueError, match="did you mean"):
        check_facts("some", "thing", {typo: True})


def test_the_refusal_names_the_adapter_and_the_observation():
    with pytest.raises(ValueError, match="some/thing"):
        check_facts("some", "thing", {"alwayson": True})


@pytest.mark.parametrize("value", ["no", "false", "", 0, 1, None, [], {}])
def test_a_general_boolean_fact_must_actually_be_a_boolean(value):
    # `bool("no")` is True, so a string here inverts the meaning of the fact
    # rather than merely being untidy.
    with pytest.raises(ValueError, match="present"):
        check_facts("some", "thing", {"present": value})


def test_governed_by_must_be_a_string():
    with pytest.raises(ValueError, match="governed_by"):
        check_facts("some", "thing", {"governed_by": ["pkg-brew/gh"]})


def test_every_shipped_adapter_fact_name_survives_the_check():
    # The check must never fire on the adapters this build ships, so the real
    # fact vocabulary is exercised rather than assumed.
    real = {
        "launchd": {"loaded": True, "running": False, "pid": None, "keepalive": True,
                    "run_at_load": True, "drifted": False, "always_on": True,
                    "present": True, "plist_path": "/x", "logs": ["/l"]},
        "mcp": {"sources": ["a"], "wirings": [{"client": "a", "scope": "user"}],
                "command": "npx", "logs": ["/l"]},
        "footprint": {"present": True, "footprints": [{"path": "~/x"}],
                      "governed_by": "pkg-brew/gh"},
        "harness": {"present": True, "kind": "hook", "always_on": True,
                    "event": "PreToolUse", "harness": "h", "profiles": ["~/.h"],
                    "runs": "~/.h/x.sh"},
        "secrets": {"configured": True, "present": True},
        "manual": {"attested_at": "2026-01-01", "stale": False},
        "chezmoi": {"drifted": True, "present": True},
    }  # fmt: skip
    for adapter, facts in real.items():
        check_facts(adapter, "sample", facts)
