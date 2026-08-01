"""Instance resolution for every verb, with the suspicious-resolution note."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from planeops.core.locate import resolve_instance_root


def instance_root(args: argparse.Namespace) -> Path:
    """Resolve the instance root for a verb, noting a suspicious resolution: a
    directory without the `.planeops` marker is almost always a fresh user who
    skipped `plane init` (or a mistyped --repo), about to scatter observed/
    state into a random directory. The note is stderr-only so pipes stay clean."""
    repo = resolve_instance_root(args.repo)
    if not (repo / ".planeops").exists():
        print(
            f"note: {repo} has no .planeops marker; run `plane init` to make it "
            "an instance (continuing anyway)",
            file=sys.stderr,
        )
    return repo
