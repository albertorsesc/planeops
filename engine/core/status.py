"""`plane status`: read the last drift report without recomputing.

A pure, instant pull of the durable drift state the scheduled reconcile already
wrote (`observed/<host>/DRIFT.json`), so a shell prompt, a status line, or a quick
check can see "is there drift?" without scanning the machine. `plane drift`
recomputes and writes the panes; `plane status` only reads the last one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.core.contracts import Platform
from engine.core.statefile import read_host_json


def read_status(
    repo_root: Path, *, platform: Platform | None = None
) -> dict[str, Any] | None:
    """The last drift report for this host, parsed from `DRIFT.json`, or None if no
    report has been written yet. Reads only; never scans the machine or writes. An
    unreadable, half-written, or non-object file reads as "no report", so a shell
    prompt calling `plane status --short` never sees a traceback."""
    return read_host_json(repo_root, "DRIFT.json", platform=platform)
