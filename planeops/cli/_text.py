"""Tiny shared output formatting for the CLI verbs."""

from __future__ import annotations

from datetime import datetime


def n_entries(n: int) -> str:
    return f"{n} entry" if n == 1 else f"{n} entries"


def human_ts(iso: object) -> str:
    """An ISO timestamp for human eyes: `16:52` when it is today, else
    `2026-08-05 16:52`. Anything unparseable passes through untouched, so a
    hand-edited report degrades instead of crashing a render."""
    if not isinstance(iso, str):
        return "?"
    try:
        ts = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if ts.date() == datetime.now().date():
        return ts.strftime("%H:%M")
    return ts.strftime("%Y-%m-%d %H:%M")
