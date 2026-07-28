"""sops+age secrets store, presence only.

A sops-encrypted YAML keeps its KEYS in plaintext and encrypts only the VALUES,
so whether a secret is configured can be checked without the age key and without
ever decrypting a value. This backend reads the key set and nothing else; there
is no code path here that returns or exposes a secret value.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class SopsBackend:
    name = "sops"

    def __init__(self, store_path: Path):
        self._store = store_path

    def _keys(self) -> set[str]:
        if not self._store.is_file():
            return set()
        try:
            data = yaml.safe_load(self._store.read_text())
        except (yaml.YAMLError, OSError):
            return set()
        if not isinstance(data, dict):
            return set()
        # `sops` is the encryption-metadata block, not a secret.
        return {k for k in data if isinstance(k, str) and k != "sops"}

    def exists(self, name: str) -> bool:
        return name in self._keys()

    def meta(self, name: str) -> dict[str, Any] | None:
        return {"configured": True} if self.exists(name) else None
