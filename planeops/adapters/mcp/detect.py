"""Detection mechanism for `plane mcp init`: which discovered clients are
actually on this machine. No client is named here: each lives in its own
module under `clients/` (the seam), and this walks whatever discovery finds.
A client counts as present only when its CONFIG exists and the CLIENT itself
is installed (binary on PATH or app bundle), so a remnant config from an
uninstalled tool is never wired."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from planeops.adapters.mcp.clients import discover_clients


def detect_sources(
    home: Path,
    *,
    which: Callable[[str], str | None] = shutil.which,
    app_root: Path = Path("/Applications"),
) -> list[dict[str, Any]]:
    """Source mappings for every discovered client that is installed and has
    its config under `home`, ordered by label for stable output."""
    found: list[dict[str, Any]] = []
    clients = discover_clients()
    for label in sorted(clients):
        c = clients[label]
        if not (home / c.config).is_file():
            continue
        installed = bool(c.binary and which(c.binary)) or bool(
            c.app and (app_root / c.app).exists()
        )
        if not installed:
            continue
        # No `logs` in the proposal: a known-client label derives its log
        # template at read time, so the config never goes stale.
        found.append(
            {
                "label": c.label,
                "path": f"~/{c.config}",
                "format": c.format,
                "key": c.key,
            }
        )
    return found
