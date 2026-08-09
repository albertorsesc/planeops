"""The write side of the mcp adapter: unwiring a retired server from the
clients that still carry it.

Everything here is guarded, because the files being written belong to other
tools and may be that tool's only copy of its own state:

- Writes are opt-in per instance (`mcp.manage: true` in instance.yaml): an
  entry marked retired under the adapter's old observe-only contract must
  not become a mutation target by mere upgrade.
- Only user-scope wirings of clients that declare an editor are planned;
  project and repo scopes are named in the preview as left alone (committed
  files belong to their repos).
- The plan carries sha256 digests of the exact file bytes and the exact
  block it previewed; execute re-reads and refuses on any mismatch, so a
  config that changed after the preview produces a loud refusal, never a
  silent write of something the human did not see.
- The file must round-trip byte-identically through this writer's own
  serialization before it is touched; a config in any other style is
  refused rather than reformatted.
- The removed block is written verbatim to a backup outside the instance
  repo before the file changes: it may hold `env` values that exist nowhere
  else. Diffs and results carry names and paths only, never block bodies:
  the journal is committed to the instance repo.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from planeops.adapters.mcp import resolve_path
from planeops.adapters.mcp.clients import KnownClient, discover_clients
from planeops.config import section as instance_section
from planeops.core.contracts import Change, Ctx, Result
from planeops.core.schema import ABSENT_LIFECYCLES, Entry
from planeops.core.statefile import atomic_write_foreign

BACKUP_DIR = Path.home() / ".local" / "state" / "planeops" / "backups"


def _client(label: str) -> KnownClient | None:
    return discover_clients().get(label)


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate key {k!r}")
        out[k] = v
    return out


def _read_strict(path: Path) -> tuple[str, dict[str, Any]]:
    """The write path's own reader: refuses everything the observe reader
    tolerates. Returns the raw bytes-as-text and the parsed mapping only when
    the file exists, parses to an object with no duplicate keys, and
    round-trips byte-identically through this writer's serialization."""
    if not path.is_absolute():
        raise ValueError(f"{path} is not absolute; refusing to write")
    if not path.is_file():
        raise ValueError(f"{path} does not exist; re-run `plane observe`")
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw, object_pairs_hook=_no_duplicates)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{path} is not writable JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object; refusing to write")
    if _dump(data) != raw:
        raise ValueError(
            f"{path} uses a serialization this writer cannot reproduce; edit it by hand"
        )
    return raw, data


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _block_sha(block: Any) -> str:
    return _sha(json.dumps(block, sort_keys=True, ensure_ascii=False))


def manage_enabled(repo_root: Path | None) -> bool:
    return instance_section(repo_root, "mcp").get("manage") is True


def plan_unwire(
    entry: Entry,
    obs_facts: dict[str, Any],
    ctx: Ctx,
    sources: list[Any],
) -> list[Change]:
    """One Change for the whole server: every writable user-scope wiring as a
    target with its digests, every other wiring named as left alone."""
    if entry.lifecycle not in ABSENT_LIFECYCLES:
        return []
    if not manage_enabled(ctx.repo_root):
        return []
    wirings = obs_facts.get("wirings")
    if not isinstance(wirings, list):
        return []  # pre-upgrade snapshot: re-observe before converging

    by_label = {s.label: s for s in sources}
    home = ctx.platform.home()
    name = entry.native_id
    targets: list[dict[str, str]] = []
    skipped: list[str] = []
    for w in wirings:
        client_label, scope = w.get("client"), w.get("scope")
        source = by_label.get(client_label)
        client = _client(client_label) if source else None
        if (
            scope != "user"
            or source is None
            or client is None
            or client.remove_server is None
        ):
            skipped.append(
                f"{client_label} {scope}" if scope != "user" else client_label
            )
            continue
        path = resolve_path(source.path, home)
        raw, data = _read_strict(path)  # raises into the failed-plan record
        servers = data.get(source.key)
        if not isinstance(servers, dict) or name not in servers:
            continue  # wiring gone since the snapshot; nothing to plan here
        targets.append(
            {
                "label": source.label,
                "path": str(path),
                "key": source.key,
                "sha_file": _sha(raw),
                "sha_block": _block_sha(servers[name]),
            }
        )
    if not targets:
        return []

    lines = [
        f"mcp: unwire {name!r} from "
        + ", ".join(f"{t['label']} ({t['path']})" for t in targets)
        + f" (listed {entry.lifecycle.value}, still wired)"
    ]
    for s in skipped:
        lines.append(f"  leaves {s} untouched (out of scope for this writer)")
    return [
        Change(
            entry_id=entry.id,
            kind="remove",
            diff="\n".join(lines),
            action={"op": "unwire", "name": name, "targets": targets},
        )
    ]


def execute_unwire(change: Change, ctx: Ctx) -> Result:
    name = str(change.action["name"])
    written: list[str] = []
    for t in change.action["targets"]:
        path = Path(t["path"])
        try:
            raw, data = _read_strict(path)
        except ValueError as exc:
            return _refused(written, str(exc))
        if _sha(raw) != t["sha_file"]:
            return _refused(
                written,
                f"{path} changed since the preview you approved; "
                "re-run `plane observe` and apply again",
            )
        servers = data[t["key"]]
        if _block_sha(servers[name]) != t["sha_block"]:
            return _refused(
                written,
                f"{name!r} in {path} changed since the preview you approved; "
                "re-run `plane observe` and apply again",
            )
        client = _client(t["label"])
        if client is None or client.remove_server is None:
            return _refused(written, f"client {t['label']!r} lost its editor")
        _backup(name, t["label"], path, servers[name])
        new_data = client.remove_server(data, t["key"], name)
        atomic_write_foreign(path, _dump(new_data))
        written.append(f"{t['label']} ({path})")
    detail = f"unwired {name!r} from " + ", ".join(written)
    detail += "; a running client keeps serving it until restarted"
    return Result(ok=True, detail=detail)


def _refused(written: list[str], why: str) -> Result:
    prefix = f"wrote {', '.join(written)}; then " if written else ""
    return Result(ok=False, detail=prefix + why)


def _backup(name: str, label: str, path: Path, block: Any) -> None:
    """The removed block, verbatim, outside the instance repo: it may hold
    env values that exist nowhere else. Owner-only, like the store files."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(BACKUP_DIR, 0o700)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "file": str(path),
        "server": name,
        "client": label,
        "block": block,
    }
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", f"{label}-{name}")
    out = BACKUP_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{safe}.json"
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
