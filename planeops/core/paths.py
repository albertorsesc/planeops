"""Path resolution against a platform's home, shared by every adapter that
reads user-relative locations from instance.yaml."""

from __future__ import annotations

from pathlib import Path


def resolve_path(path_str: str, home: Path) -> Path:
    """A configured path resolved against the platform's home, not the
    process's, so a fake platform in tests confines every read to its own
    tree."""
    if path_str == "~":
        return home
    if path_str.startswith("~/"):
        return home / path_str[2:]
    return Path(path_str)
