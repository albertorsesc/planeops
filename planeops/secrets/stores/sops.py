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

from planeops._run import Runner, default_run
from planeops.providers import yaml

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
            data = yaml.load(self._store.read_text())
        except (yaml.ParseError, OSError):
            return set()
        if not isinstance(data, dict):
            return set()
        # A store that is not actually encrypted must be refused, never
        # blessed: a failed `sops -e` leaves plaintext behind, and presence
        # answering "configured" over cleartext would hide exactly the leak
        # this store exists to prevent. The raise lands as a failed-scan
        # alert. Every non-metadata value must be an ENC[...] string and the
        # `sops` metadata block must exist.
        secrets = {k: v for k, v in data.items() if k != "sops"}
        plaintext = [
            k
            for k, v in secrets.items()
            if not (isinstance(v, str) and v.startswith("ENC["))
        ]
        if secrets and ("sops" not in data or plaintext):
            raise ValueError(
                f"secrets store {self._store} is not encrypted "
                f"(plaintext values: {sorted(plaintext) or 'missing sops metadata'}); "
                "encrypt it: cd into the instance, then `sops -e -i "
                f"{self._store.name}`"
            )
        return {k for k in secrets if isinstance(k, str)}

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
            # Keep the TAIL of stderr: sops puts the actionable part (which
            # identity paths it searched) last, and the head is boilerplate.
            # The identity hint only helps identity-shaped failures; on a
            # malformed store it points the user away from the real problem.
            err = res.err.strip()
            hint = (
                ""
                if "metadata" in err
                else " (if the age identity lives outside sops's default "
                "path, set SOPS_AGE_KEY_FILE)"
            )
            raise RuntimeError(
                f"sops decrypt failed for {name!r}: ...{err[-300:]}{hint}"
            )
        return res.out.rstrip("\n")


def _sops_default_key_file(home: Path) -> Path:
    """Where sops itself looks for age identities (its os.UserConfigDir rule),
    so a bootstrapped setup decrypts with no environment variable at all."""
    import sys

    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "sops" / "age" / "keys.txt"
    return home / ".config" / "sops" / "age" / "keys.txt"


def _recipient_from(key_file: Path) -> str | None:
    if not key_file.is_file():
        return None
    for line in key_file.read_text().splitlines():
        if "public key:" in line:
            return line.split("public key:")[1].strip()
    return None


class _SopsBootstrap:
    """Mixed into the provider: creates identity, rules, and the encrypted
    store. Every sops call passes --config explicitly: the working directory
    can never matter."""

    def _paths(
        self, repo_root: Path, age_key_file: Path | None
    ) -> tuple[Path, Path, Path]:
        key = age_key_file or _sops_default_key_file(Path.home())
        return key, repo_root / ".sops.yaml", repo_root / DEFAULT_PATH

    def bootstrap_preview(
        self, repo_root: Path, *, age_key_file: Path | None
    ) -> list[str]:
        key, rules, store = self._paths(repo_root, age_key_file)
        lines = []
        if _recipient_from(key) is None:
            lines.append(f"{key} (new age identity via age-keygen)")
        else:
            lines.append(f"{key} (existing identity, reused)")
        lines.append(f"{rules} (sops creation rule for this store)")
        lines.append(f"{store} (empty encrypted store)")
        return lines

    def bootstrap(self, repo_root: Path, *, age_key_file: Path | None) -> list[str]:
        key, rules, store = self._paths(repo_root, age_key_file)
        if store.exists():
            raise LookupError(
                f"a store already exists at {store}; re-initializing would "
                "orphan its values, so delete it yourself first if you mean it"
            )
        actions: list[str] = []
        recipient = _recipient_from(key)
        if recipient is None:
            key.parent.mkdir(parents=True, exist_ok=True)
            res = default_run(["age-keygen", "-o", str(key)], timeout=30)
            if res.code != 0:
                detail = res.err.strip()[-200:] or "is age installed?"
                raise LookupError(f"age-keygen failed: {detail}")
            recipient = _recipient_from(key)
            if recipient is None:
                raise LookupError(f"no public key found in {key} after age-keygen")
            actions.append(f"created age identity {key}")
        else:
            actions.append(f"reusing age identity {key}")
        rules.write_text(
            "creation_rules:\n"
            f"  - path_regex: {DEFAULT_PATH.replace('.', chr(92) + '.')}$\n"
            f"    age: {recipient}\n"
        )
        actions.append(f"wrote {rules}")
        store.write_text("{}\n")
        res = default_run(
            ["sops", "--config", str(rules), "-e", "-i", str(store)], timeout=30
        )
        if res.code != 0:
            store.unlink(missing_ok=True)  # never leave a plaintext husk behind
            raise LookupError(
                f"sops encrypt failed: {res.err.strip()[-200:] or 'is sops installed?'}"
            )
        actions.append(f"created encrypted store {store}")
        return actions


class SopsProvider(_SopsBootstrap):
    """The discovery face of this store: name, default status, construction."""

    name = "sops"
    is_default = True  # the shipped default; a second store would ship False

    def build(self, repo_root: Path, section: dict[str, Any]) -> SopsStore:
        configured = section.get("path")
        rel = configured if isinstance(configured, str) and configured else DEFAULT_PATH
        return SopsStore(repo_root / rel)


STORE = SopsProvider()
