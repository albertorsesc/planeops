"""The instance config file (`instance.yaml`): how this machine's adapters read.

Three kinds of config live in an instance, separated for different reasons:

- `registry/*.yaml` is desired state (what should exist), authored by a human and
  split across as many files as they like; the engine unions them.
- a sops store holds encrypted secret values, a hard file boundary (plaintext
  entries and ciphertext can't share one document).
- this file, `instance.yaml`, holds the third thing: per-adapter settings that say
  where and how each adapter reads *this* machine (which tool configs the `mcp`
  adapter scans, the `import` mapping, the secrets store path).

One file, one section per concern, so the next adapter that needs a knob has an
obvious home instead of a new root-level file. Missing file, missing section, or
malformed content degrades to an empty mapping, so every adapter falls back to its
own defaults rather than failing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

INSTANCE_FILE = "instance.yaml"


def load_instance(repo_root: Path | None) -> dict[str, Any]:
    """Parse `<repo_root>/instance.yaml`. Any problem (no root, no file, malformed,
    or a non-mapping document) yields an empty mapping."""
    if repo_root is None:
        return {}
    path = repo_root / INSTANCE_FILE
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text())
    except (yaml.YAMLError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def section(repo_root: Path | None, name: str) -> dict[str, Any]:
    """Return the named top-level section as a mapping (empty if absent or not a
    mapping), so a caller can `.get()` its keys without re-checking types."""
    value = load_instance(repo_root).get(name)
    return value if isinstance(value, dict) else {}
