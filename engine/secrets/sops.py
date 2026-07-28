"""sops+age secrets store.

A sops-encrypted YAML keeps its KEYS in plaintext and encrypts only the VALUES,
so whether a secret is configured can be checked without the age key and without
decrypting anything: `exists`/`meta` read the key set only. Decrypting one value
(`get`) shells out to `sops` and is reached only through an unsealed handle, so it
never runs during observe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from engine.adapters._run import Runner, default_run


class SopsBackend:
    name = "sops"

    def __init__(self, store_path: Path, run: Runner = default_run):
        self._store = store_path
        self._run = run

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

    def get(self, name: str) -> str:
        """Decrypt one value via `sops -d --extract`. Raises if the key is absent
        or sops fails, so a caller never silently materializes an empty secret."""
        if not self.exists(name):
            raise KeyError(f"secret {name!r} is not configured in {self._store}")
        res = self._run(["sops", "-d", "--extract", f'["{name}"]', str(self._store)])
        if res.code != 0:
            # Cap stderr: it flows into an operator-facing error, not a value.
            raise RuntimeError(
                f"sops decrypt failed for {name!r}: {res.err.strip()[:200]}"
            )
        return res.out.rstrip("\n")
