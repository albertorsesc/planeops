"""Which documented instance sections an existing instance has not adopted.

`plane init` writes the starter instance.yaml once and then keeps its hands
off, which is right: the file is the operator's. The cost is that an instance
created before an adapter existed never learns the adapter has a section, and
the only hint is reading the shipped example and diffing it by eye.

This answers that question from the example this build carries, so an
installed `plane` reports the adapters that build actually ships. It hands
back the documented block, header comment and all, for the operator to paste.
Nothing here writes: a config file that edits itself is one the operator no
longer knows the shape of.
"""

from __future__ import annotations

import re
from importlib.resources import files

# Each section in the example opens with a banner comment and runs until the
# next one. The banner is what makes a block self-explaining once pasted.
_BANNER = re.compile(r"^# --- ")
# A top-level key, whether the example ships it enabled or commented out.
_TOP_KEY = re.compile(r"^#?\s?([a-z][a-z0-9_-]*):\s*$")


def _example_text() -> str:
    return (files("planeops") / "instance.example.yaml").read_text(encoding="utf-8")


def documented_sections(example: str | None = None) -> dict[str, str]:
    """section name -> its block in the example, banner comment included."""
    text = example if example is not None else _example_text()
    blocks: dict[str, str] = {}
    current: list[str] = []

    def close() -> None:
        if not current:
            return
        for line in current:
            m = _TOP_KEY.match(line)
            if m:
                blocks[m.group(1)] = "\n".join(current).strip("\n") + "\n"
                return

    for line in text.split("\n"):
        if _BANNER.match(line):
            close()
            current = [line]
        elif current:
            current.append(line)
    close()
    return blocks


def configured_sections(instance: str) -> set[str]:
    """The top-level keys an instance actually sets. Parsed from the text
    rather than the loaded mapping, so a file that does not parse yields
    nothing configured and every section reads as missing, which is the safe
    direction: it offers too much rather than hiding a section behind a
    syntax error."""
    out: set[str] = set()
    for line in instance.split("\n"):
        if line.startswith("#"):
            continue  # commented out is not configured; it is switched off
        m = _TOP_KEY.match(line)
        if m:
            out.add(m.group(1))
    return out


def missing_sections(
    instance: str, example: str | None = None
) -> list[tuple[str, str]]:
    """(name, block) for every documented section this instance does not set,
    in the example's own order so the pasted result reads like the reference."""
    have = configured_sections(instance)
    return [(n, b) for n, b in documented_sections(example).items() if n not in have]
