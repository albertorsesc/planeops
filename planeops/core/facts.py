"""The general facts the triage understands, and the check that they are real.

`Observed.facts` is open on purpose: an adapter records whatever its domain
needs, and the engine reads only the handful of names below (SPEC.md section
4). That openness is what makes a mistake quiet. A fact named `alwayson` is
not rejected as unknown, because unknown is legitimate; it simply never
reaches the code that would have acted on it, so a service that runs at login
is never called out. A `present` that is the string "no" is worse, because
`bool("no")` is true and the fact then means the opposite of what it says.

So this checks the two things that are decidable without closing the door:
a general fact carrying the wrong type, and a name that is one of the general
ones written with different case or separators. The second rule is deliberately
exact rather than approximate, because `present_at` and `configured_by` are the
ordinary way to name a related domain fact and must keep working. Whatever an
adapter wants to record of its own passes untouched, which is why `pid`,
`wirings` and `footprints` are none of this module's business.

This is the guard for the adapter seam, where third-party code produces facts
the engine never sees at type-check time. First-party adapters go through
`Observed.of`, whose keyword arguments turn the same mistakes into mypy errors
at the call site, and which catches the misspellings an exact rule cannot.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# Name -> the type the triage expects. Every reader in core keys off one of
# these, so this table is the vocabulary, and adding to it means teaching the
# triage to act on it. `Observed.of` mirrors this table as its keyword
# arguments, and a test pins the two together.
GENERAL: dict[str, type] = {
    "present": bool,  # semantic presence; absent fact means observed IS present
    "drifted": bool,  # content or definition drift, tolerance-routed
    "always_on": bool,  # will run code at login or on a schedule
    "stale": bool,  # attestation age
    "configured": bool,  # secret presence
    "governed_by": str,  # id of the declared entry this is evidence for
}

_SEPARATORS = re.compile(r"[^a-z0-9]+")


def _canonical(name: str) -> str:
    """A fact name reduced to letters and digits, so the spellings a person
    reaches for (`alwayson`, `always-on`, `Always On`) land on one key while a
    name with anything more to it (`always_running`) stays distinct."""
    return _SEPARATORS.sub("", name.lower())


_BY_CANONICAL: dict[str, str] = {_canonical(name): name for name in GENERAL}


def check_facts(adapter: str, native_id: str, facts: Mapping[str, Any]) -> None:
    """Raise when a fact would silently do nothing or silently lie."""
    for key, value in facts.items():
        expected = GENERAL.get(key)
        if expected is not None:
            # `isinstance(True, int)` is true, so a bool fact given 1 or 0 is
            # caught here too: the triage tests these with `bool(...)`, and a
            # value that is not already one hides a conversion nobody wrote.
            if type(value) is not expected:
                raise ValueError(
                    f"{adapter}/{native_id}: fact {key!r} must be "
                    f"{expected.__name__}, got {type(value).__name__} ({value!r})"
                )
            continue
        intended = _BY_CANONICAL.get(_canonical(str(key)))
        if intended is not None:
            raise ValueError(
                f"{adapter}/{native_id}: fact {key!r} is not one the triage "
                f"reads; write it as {intended!r} (an adapter may record any "
                f"other name it likes)"
            )
