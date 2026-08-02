"""Tiny shared output formatting for the CLI verbs."""

from __future__ import annotations


def n_entries(n: int) -> str:
    return f"{n} entry" if n == 1 else f"{n} entries"
