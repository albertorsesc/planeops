"""The general facts the triage understands, and the check that they are real.

`Observed.facts` is open on purpose: an adapter records whatever its domain
needs, and the engine reads only the handful of names below (SPEC.md section
4). That openness is what makes a mistake quiet. A fact named `alwayson` is
not rejected as unknown, because unknown is legitimate; it simply never
reaches the code that would have acted on it, so a service that runs at login
is never called out. A `present` that is the string "no" is worse, because
`bool("no")` is true and the fact then means the opposite of what it says.

So this checks the two things that are decidable without closing the door:
a name close enough to a general fact to be a typo of it, and a general fact
carrying the wrong type. Anything else an adapter wants to record passes
untouched, which is why `pid`, `wirings` and `footprints` are none of this
module's business.
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping
from typing import Any

# Name -> the type the triage expects. Every reader in core keys off one of
# these, so this table is the vocabulary, and adding to it means teaching the
# triage to act on it.
GENERAL: dict[str, type] = {
    "present": bool,  # semantic presence; absent fact means observed IS present
    "drifted": bool,  # content or definition drift, tolerance-routed
    "always_on": bool,  # will run code at login or on a schedule
    "stale": bool,  # attestation age
    "configured": bool,  # secret presence
    "governed_by": str,  # id of the declared entry this is evidence for
}

# Close enough to be a typo, far enough that no shipped adapter fact trips it.
# Measured against every fact name in the tree: the nearest miss is well below
# this, so the check refuses typos without narrowing what an adapter may say.
_TYPO_CUTOFF = 0.8


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
        close = difflib.get_close_matches(str(key), GENERAL, n=1, cutoff=_TYPO_CUTOFF)
        if close:
            raise ValueError(
                f"{adapter}/{native_id}: fact {key!r} is not one the triage "
                f"reads; did you mean {close[0]!r}? (an adapter may record any "
                f"other name it likes)"
            )
