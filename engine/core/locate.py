"""Locate the instance root: where `registry/` + `observed/` live for this run.

An installed `plane` must find its instance from any working directory, so the root
resolves by precedence (first hit wins):

  1. `--repo <path>`       explicit, always wins
  2. `$PLANEOPS_INSTANCE`   env override
  3. `~/.config/planeops/config.toml`  ->  `instance = "<path>"`  (honors
     `$XDG_CONFIG_HOME`)
  4. the current directory, walking up to a `.planeops` marker

The home config dir holds only this pointer (and host prefs), never generated state:
state stays under the resolved instance (`<root>/observed/<host>/...`), keeping the
engine/instance split and multi-host-in-one-repo intact.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path

MARKER = ".planeops"


def find_repo_root(start: Path) -> Path:
    """Walk up from `start` to the directory holding the `.planeops` marker; if none
    is found, `start` itself is the root."""
    for candidate in (start, *start.parents):
        if (candidate / MARKER).exists():
            return candidate
    return start


def config_home(env: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """The planeops config dir: `$XDG_CONFIG_HOME/planeops` if set, else
    `~/.config/planeops`. Config only, never state."""
    m: Mapping[str, str] = os.environ if env is None else env
    xdg = m.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else (home or Path.home()) / ".config"
    return base / "planeops"


def _instance_from_config(env: Mapping[str, str], home: Path | None) -> Path | None:
    cfg = config_home(env, home) / "config.toml"
    if not cfg.is_file():
        return None
    try:
        data = tomllib.loads(cfg.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None  # a broken config never crashes a run; it just doesn't point
    inst = data.get("instance")
    return Path(inst).expanduser() if isinstance(inst, str) and inst else None


def resolve_instance_root(
    cli_repo: str | None,
    *,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    cwd: Path | None = None,
) -> Path:
    """Resolve the instance root by the documented precedence. `env`/`home`/`cwd` are
    injectable for testing and default to the real process values."""
    m: Mapping[str, str] = os.environ if env is None else env
    if cli_repo is not None:
        base = Path(cli_repo)
    elif m.get("PLANEOPS_INSTANCE"):
        base = Path(m["PLANEOPS_INSTANCE"])
    elif (from_cfg := _instance_from_config(m, home)) is not None:
        base = from_cfg
    else:
        base = cwd or Path.cwd()
    return find_repo_root(base.expanduser().resolve())
