"""sops+age secrets store.

A sops-encrypted YAML keeps its KEYS in plaintext and encrypts only the VALUES,
so whether a secret is configured can be checked without the age key and without
decrypting anything: `exists`/`meta` read the key set only. Decrypting one value
(`get`) shells out to `sops` and is reached only through an unsealed handle, so it
never runs during observe.

Selected as `secrets: {store: sops}` in `instance.yaml` (and by default: this
module declares itself the default store, the resolution layer holds no such
knowledge). Its one knob is `secrets.sops.path`, the store file relative to the
instance root; a provider sees only its own `secrets.<name>` sub-mapping.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from planeops._run import Runner, default_run

# At the instance ROOT, deliberately not inside registry/: registry files are
# declared entries and globs, strictly validated as such; the encrypted store
# is a different kind of document and cohabiting only ever worked by accident.
DEFAULT_PATH = "secrets.sops.yaml"


class SopsStore:
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
        if any(c in name for c in '"\\') or not name.isprintable():
            # The name lands inside the --extract expression '["<name>"]'; a
            # quote, backslash, or control character could change what gets
            # extracted. No legitimate secret name needs them.
            raise ValueError(
                f"secret name {name!r} cannot be safely quoted for extraction"
            )
        if not self.exists(name):
            raise KeyError(f"secret {name!r} is not configured in {self._store}")
        # Decrypt can wait on an age key or a pinentry, but must not wedge an
        # apply forever: bounded, above the seam's 30s default.
        res = self._run(
            ["sops", "-d", "--extract", f'["{name}"]', str(self._store)],
            timeout=60,
        )
        if res.code != 0:
            # Cap stderr: it flows into an operator-facing error, not a value.
            raise RuntimeError(
                f"sops decrypt failed for {name!r}: {res.err.strip()[:200]}"
            )
        return res.out.rstrip("\n")


class SopsProvider:
    """The discovery face of this store: name, default status, construction."""

    name = "sops"
    is_default = True  # the shipped default; a second store would ship False

    def build(self, repo_root: Path, section: dict[str, Any]) -> SopsStore:
        configured = section.get("path")
        rel = configured if isinstance(configured, str) and configured else DEFAULT_PATH
        return SopsStore(repo_root / rel)


STORE = SopsProvider()
