"""secrets adapter: presence observation and value materialization.

observe reports, per declared `secrets/<name>` entry, whether the secret is
configured (presence only, never a value). plan/execute materialize a configured
secret into the injection targets that OTHER entries declare through their
`secrets` refs (`injected_as: file:<path>#KEY`): planning a `secrets/<name>` entry
scans the registry for consumers of that secret and proposes a value-redacted
write per target; execute pulls the value from the unsealed handle and writes it
to the file. The value never enters the diff, the journal, a snapshot, or a report.
"""

from __future__ import annotations

import contextlib
import errno
import os
from pathlib import Path
from typing import Any, Protocol

from engine.config import section as instance_section
from engine.core.contracts import Change, Ctx, Observed, Result
from engine.core.schema import Entry
from engine.secrets import SecretsBackend
from engine.secrets.store import build_handle


class _Reader(Protocol):
    """Anything that can answer presence for the observe pass (a backend or the
    handle on Ctx both structurally satisfy this)."""

    def exists(self, name: str) -> bool: ...


class SecretsAdapter:
    name = "secrets"
    domains: tuple[str, ...] = ("secret",)
    # Materialize before phase-6 services load, so their config is complete. Used
    # when an entry sets no explicit phase (mirrors the SPEC converge order).
    default_phase = 5

    def __init__(self, backend: SecretsBackend | None = None):
        self._backend = backend

    def _reader(self, ctx: Ctx) -> _Reader | None:
        # An injected backend (tests) wins; then the handle the engine put on Ctx;
        # else resolve one from the repo. All expose exists() for presence.
        if self._backend is not None:
            return self._backend
        if ctx.secrets is not None:
            return ctx.secrets
        return build_handle(ctx.repo_root)

    def observe(self, ctx: Ctx) -> list[Observed]:
        reader = self._reader(ctx)
        if reader is None:
            return []
        return [
            Observed(
                adapter=self.name,
                native_id=entry.native_id,
                facts={"configured": reader.exists(entry.native_id)},
                version=None,
            )
            for entry in ctx.entries
            if entry.adapter == self.name
        ]

    def plan(
        self, entry: Entry, obs: Observed | None, ctx: Ctx | None = None
    ) -> list[Change]:
        if ctx is None:
            return []
        home = ctx.platform.home() if ctx.platform is not None else Path.home()
        changes: list[Change] = []
        for path_str, key in _targets_for(entry.native_id, ctx.entries):
            target = _resolve(path_str, home)
            if _has_key(target, key):
                continue  # already materialized; rotation is a separate concern
            changes.append(
                Change(
                    entry_id=entry.id,
                    kind="configure",
                    diff=(
                        f"materialize secret {entry.native_id} -> "
                        f"{path_str} as {key} (value redacted)"
                    ),
                    action={"name": entry.native_id, "path": str(target), "key": key},
                )
            )
        return changes

    def execute(self, change: Change, ctx: Ctx) -> Result:
        if ctx.secrets is None:
            return Result(ok=False, detail="no secrets store resolved")
        name = str(change.action["name"])
        target = Path(str(change.action["path"]))
        key = str(change.action["key"])
        # Containment: resolve the target's parent (following legitimate symlinks)
        # and refuse if it escapes the allowed injection bases, so a symlinked
        # ancestor can't redirect the value out of trusted space.
        real_parent = Path(os.path.realpath(target.parent))
        if not _within(real_parent, _allowed_bases(ctx)):
            return Result(
                ok=False,
                detail=f"refusing to materialize outside the allowed bases: {target}",
            )
        try:
            # Raises unless this is the engine's materialization handle (secrets
            # adapter, post-confirmation); fail closed rather than proceed.
            value = ctx.secrets.get(name)
        except Exception as exc:
            return Result(ok=False, detail=f"could not read secret {name}: {exc}")
        dest = real_parent / target.name
        try:
            _upsert_env(real_parent, target.name, key, value)
        except Exception as exc:  # symlink refusal, write/replace failure, etc.
            return Result(ok=False, detail=f"could not materialize {key}: {exc}")
        return Result(ok=True, detail=f"materialized {key} -> {dest} (value redacted)")


def _targets_for(name: str, entries: tuple[Entry, ...]) -> list[tuple[str, str]]:
    """(path, key) targets declared by any entry whose `secrets` refs point at
    this secret with an `injected_as: file:<path>#KEY`."""
    out: list[tuple[str, str]] = []
    for e in entries:
        for ref in e.secrets:
            if not isinstance(ref, dict) or _ref_name(ref.get("ref")) != name:
                continue
            target = _file_target(ref.get("injected_as"))
            if target is not None:
                out.append(target)
    return out


def _ref_name(ref: Any) -> str | None:
    if not isinstance(ref, str) or not ref.startswith("secret://"):
        return None
    rest = ref[len("secret://") :]
    return rest.split("/", 1)[1] if "/" in rest else rest


def _file_target(injected_as: Any) -> tuple[str, str] | None:
    if not isinstance(injected_as, str) or not injected_as.startswith("file:"):
        return None  # only file targets in this slice; env: is deferred
    body = injected_as[len("file:") :]
    if "#" not in body:
        return None
    path, key = body.rsplit("#", 1)
    return (path, key) if path and key else None


def _resolve(path_str: str, home: Path) -> Path:
    if path_str == "~":
        return home
    if path_str.startswith("~/"):
        return home / path_str[2:]
    return Path(path_str)


def _has_key(target: Path, key: str) -> bool:
    if not target.is_file():
        return False
    return any(
        line.split("=", 1)[0].strip() == key for line in target.read_text().splitlines()
    )


def _allowed_bases(ctx: Ctx) -> list[Path]:
    """Directories a secret may be materialized into: the instance repo and the home
    dir by default, plus any `secrets.allow_targets` in instance.yaml. Each is
    realpath-resolved, so containment compares resolved paths to resolved bases."""
    bases: list[Path] = []
    if ctx.repo_root is not None:
        bases.append(Path(os.path.realpath(ctx.repo_root)))
    home = ctx.platform.home() if ctx.platform is not None else None
    if home is not None:
        bases.append(Path(os.path.realpath(home)))
    configured = instance_section(ctx.repo_root, "secrets").get("allow_targets")
    if isinstance(configured, list):
        for item in configured:
            if isinstance(item, str) and item:
                resolved = _resolve(item, home or Path.home())
                bases.append(Path(os.path.realpath(resolved)))
    return bases


def _within(path: Path, bases: list[Path]) -> bool:
    """True if `path` is one of `bases` or nested under one. Empty bases (nothing
    resolvable and nothing configured) means deny-by-default."""
    return any(path == base or base in path.parents for base in bases)


def _read_lines(name: str, dir_fd: int) -> list[str]:
    """Read the target's existing lines via openat with O_NOFOLLOW, so a symlink at
    the target path (including one racing a prior check) is refused, not followed.
    A missing file reads as empty."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
    except FileNotFoundError:
        return []
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise RuntimeError(
                f"refusing to materialize into a symlink: {name}"
            ) from exc
        raise
    with os.fdopen(fd, "r") as fh:
        return fh.read().splitlines()


def _upsert_env(directory: Path, name: str, key: str, value: str) -> None:
    """Set `key=value` in `directory`/`name` and replace it atomically. `directory`
    is the caller's realpath-resolved, containment-checked parent; all file ops run
    relative to its directory fd so the verified parent can't be swapped mid-write.
    The final component and temp are opened O_NOFOLLOW (a symlinked target is
    refused); the temp is created 0600 and removed on any failure."""
    directory.mkdir(parents=True, exist_ok=True)
    dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        lines = _read_lines(name, dir_fd)
        row = f"{key}={value}"
        for i, line in enumerate(lines):
            if line.split("=", 1)[0].strip() == key:
                lines[i] = row
                break
        else:
            lines.append(row)
        content = "\n".join(lines) + "\n"

        tmp = name + ".tmp"
        fd = os.open(
            tmp,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
            0o600,
            dir_fd=dir_fd,
        )
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(content)
            os.replace(tmp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp, dir_fd=dir_fd)  # never leave plaintext behind
            raise
    finally:
        os.close(dir_fd)


ADAPTER = SecretsAdapter()
