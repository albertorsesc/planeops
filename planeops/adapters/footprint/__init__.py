"""The footprint adapter: tools discovered by the config traces they leave.

A tool that writes `~/.config/<name>` exists on this machine whether or not
any package manager knows about it. Each root named in instance.yaml is
scanned one level deep and every child becomes an observation. Discovery is
stat-only: nothing is ever opened, so a footprint holding credentials
contributes its name and shape, never its contents.

Roots are configuration, `{label, path}` under `footprint.roots`; the engine
hardcodes no convention and no tool name. The example instance documents the
common conventions (XDG config, home dot-directories, per-OS app support).
No section means no scan.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from planeops.config import section as instance_section
from planeops.core.contracts import Ctx, Observed
from planeops.core.paths import resolve_path
from planeops.core.schema import reject_unknown_keys


@dataclass(frozen=True, slots=True)
class FootprintRoot:
    label: str
    path: str


_ROOT_KEYS = frozenset({"label", "path"})


def load_roots(repo_root: Path | None) -> list[FootprintRoot]:
    """Read `footprint.roots` from instance.yaml. A missing file or section
    yields no roots (opt-in); a present but malformed root raises, landing in
    the snapshot's failed-scan alert, so a typo can never quietly mean
    "observe nothing"."""
    raw = instance_section(repo_root, "footprint").get("roots")
    if not isinstance(raw, list):
        return []
    roots: list[FootprintRoot] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"footprint.roots[{i}] must be a mapping, got {item!r}")
        reject_unknown_keys(item, _ROOT_KEYS, f"footprint.roots[{i}]")
        label, path = item.get("label"), item.get("path")
        if not isinstance(label, str) or not label:
            raise ValueError(f"footprint.roots[{i}] label must be a non-empty string")
        if not isinstance(path, str) or not path:
            raise ValueError(f"footprint.roots[{i}] path must be a non-empty string")
        roots.append(FootprintRoot(label=label, path=path))
    return roots


class FootprintAdapter:
    name = "footprint"
    domains: tuple[str, ...] = ("footprint",)

    def observe(self, ctx: Ctx) -> list[Observed]:
        home = ctx.platform.home()
        out: list[Observed] = []
        for root in load_roots(ctx.repo_root):
            base = resolve_path(root.path, home)
            if not base.is_dir():
                continue  # the convention is simply not present here: quiet
            for child in sorted(base.iterdir()):
                out.append(self._observed(root, child, home))
        return out

    def _observed(self, root: FootprintRoot, child: Path, home: Path) -> Observed:
        facts: dict[str, object] = {
            "present": True,
            "kind": "dir" if child.is_dir() else "file",
            "path": _display(child, home),
            "convention": root.label,
        }
        if child.is_symlink():
            facts["symlink"] = True
        return Observed(
            adapter=self.name,
            native_id=child.name,
            facts=facts,
            version=None,
        )


def _display(path: Path, home: Path) -> str:
    """Home-relative for portability across hosts that share a layout."""
    try:
        return "~" + os.sep + str(path.relative_to(home))
    except ValueError:
        return str(path)


ADAPTER = FootprintAdapter()
