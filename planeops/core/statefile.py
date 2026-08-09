"""Durable per-host state files: write them atomically, read them torn-safely.

Every generated file under `observed/<host>/` (the snapshot, DRIFT.md, DRIFT.json)
is state a later command reads back, sometimes while another command is writing it
(a shell prompt running `plane status` mid-`plane observe`). Two invariants keep
that safe, and both live here so no writer or reader has to re-implement them:

- `atomic_write`: temp sibling + `os.replace`, so a reader sees the whole old file
  or the whole new one, never a half-written one.
- `read_host_json`: a torn, absent, or non-object file reads as "nothing yet"
  (`None`), never a traceback, so a read command degrades quietly.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from planeops.core.contracts import Platform


def atomic_write(path: Path, text: str) -> None:
    """Write `text` to `path` atomically (temp sibling then rename)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def atomic_write_foreign(path: Path, text: str) -> None:
    """Atomic write for a file planeops does NOT own (another tool's config).
    Foreign files bring hazards the state-file writer never meets: the path
    may be a symlink into a dotfiles repo (write through it, never replace
    the link with a file), the mode may be 0600 on credential-bearing content
    (preserve it, never widen), another process may be writing its own temp
    (unique temp name), and the content is the user's only copy (fsync before
    publishing)."""
    real = path.resolve()
    mode = real.stat().st_mode & 0o7777
    fd, tmp_name = tempfile.mkstemp(prefix=f".{real.name}.", dir=str(real.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, real)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


def read_json_file(path: Path) -> dict[str, Any] | None:
    """Parse `path` as a JSON object, or None if it is absent, unreadable, torn
    (mid-write), or valid JSON that is not an object. Never raises."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def read_host_json(
    repo_root: Path, filename: str, *, platform: Platform | None = None
) -> dict[str, Any] | None:
    """Parse `observed/<host>/<filename>` as a JSON object, or None if it is
    absent, unreadable, torn (mid-write), or not a JSON object. Reads only; never
    scans the machine or writes."""
    from planeops.platform import current_platform

    platform = platform or current_platform()
    return read_json_file(repo_root / "observed" / platform.hostname() / filename)
