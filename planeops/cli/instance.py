"""Instance resolution for every verb: no marker means refuse, not adopt."""

from __future__ import annotations

import argparse
from pathlib import Path

from planeops.core.locate import resolve_instance_root


def instance_root(args: argparse.Namespace) -> Path:
    """Resolve the instance root for a verb. A directory without the `.planeops`
    marker is refused: it is almost always a fresh user who skipped `plane init`
    (or a mistyped --repo), about to scatter observed/ state into a random
    directory. Only `plane init` creates instances; the LookupError lands at the
    CLI's operator-error choke point as a clean exit 1."""
    repo = resolve_instance_root(args.repo)
    if not (repo / ".planeops").exists():
        raise LookupError(
            f"{repo} is not a planeops instance (no .planeops marker); run "
            "`plane init <path>` first, or point --repo/$PLANEOPS_INSTANCE/"
            "config.toml at an initialized instance"
        )
    return repo
