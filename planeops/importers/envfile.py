"""Import secret NAMES from a `.env`-style file into proposed registry entries.

Reads only the keys; VALUES are discarded and never printed, stored, or returned.
Each key becomes a `secrets/<name>` stub (`auth: interactive`) for a human to store
in the configured secrets store and verify. Nothing is written; the CLI prints
the proposal for review. This keeps the value-free discipline of the whole
secrets path: a value from a `.env` cannot reach a snapshot, a report, or the
proposed registry.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from planeops.importers import render_proposal

# `[export ]NAME=` at the start of a line; the value (everything after `=`) is
# matched by nothing here, so it is never captured.
_ASSIGN = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def parse_envfile(text: str) -> list[str]:
    """The variable NAMES declared in a `.env` file, in order, deduplicated. Lines
    without an assignment (and comments/blanks) are skipped; values are discarded."""
    names: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        match = _ASSIGN.match(line)
        if not match:
            continue
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def entries_from_names(names: list[str]) -> list[dict[str, Any]]:
    """One `secrets/<slug>` stub per name. Interactive because the value must
    be stored in the secrets store by hand; the importer only records need."""
    return [
        {
            "id": f"secrets/{_slug(name)}",
            "adapter": "secrets",
            "domain": "secret",
            "lifecycle": "active",
            "auth": "interactive",
            "intent": (
                "imported from env file; store the value in the secrets "
                "store, then verify"
            ),
        }
        for name in names
    ]


class EnvfileImporter:
    kind = "envfile"

    def propose(self, text: str, repo_root: Path | None) -> list[dict[str, Any]]:
        return entries_from_names(parse_envfile(text))

    def note(self, path: Path, count: int) -> str:
        return (
            f"# proposed {count} secret name(s) from {path} (values discarded) "
            "- store each in the secrets store, then save into registry/"
        )


IMPORTER = EnvfileImporter()

__all__ = [
    "EnvfileImporter",
    "IMPORTER",
    "entries_from_names",
    "parse_envfile",
    "render_proposal",
]
