"""`plane status`: read the last drift report without recomputing.

A pure, instant pull of the durable drift state the scheduled reconcile already
wrote (`observed/<host>/DRIFT.json`), so a shell prompt, a status line, or a quick
check can see "is there drift?" without scanning the machine. `plane drift`
recomputes and writes the panes; `plane status` only reads the last one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.core.contracts import Platform


def read_status(
    repo_root: Path, *, platform: Platform | None = None
) -> dict[str, Any] | None:
    """The last drift report for this host, parsed from `DRIFT.json`, or None if no
    report has been written yet. Reads only; never scans the machine or writes."""
    from engine.platform import current_platform

    platform = platform or current_platform()
    path = repo_root / "observed" / platform.hostname() / "DRIFT.json"
    if not path.is_file():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        # An unreadable or half-written file reads as "no report", so a shell
        # prompt calling `plane status --short` never sees a traceback.
        return None
    return data
