"""The footprint adapter: tools discovered by the config traces they leave.

A tool that writes `~/.config/<name>` exists on this machine whether or not
any package manager knows about it. Each root named in instance.yaml is
scanned one level deep; children that name the same tool across roots merge
into one observation (`~/.ollama`, `~/.config/ollama`, and an app-support
`Ollama` are one tool with three footprints). Discovery is stat-only:
nothing is ever opened, so a footprint holding credentials contributes its
name and shape, never its contents.

Roots are configuration, `{label, path, dot_only?, os?}` under
`footprint.roots`; the engine hardcodes no convention and no tool name.
`dot_only: true` scans only dot-children, which is what makes `path: ~` mean
"home dotfiles" rather than everything in home. `os: darwin` (or any
discovered platform name) confines a root to that system, so one documented
convention block is safe to carry to every machine; the tag is validated
against the discovered platforms, so a typo fails the scan loudly instead of
silently skipping forever. No section means no scan.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from planeops.config import section as instance_section
from planeops.core.contracts import Ctx, Observed
from planeops.core.paths import resolve_path
from planeops.core.schema import reject_unknown_keys


@dataclass(frozen=True, slots=True)
class FootprintRoot:
    label: str
    path: str
    dot_only: bool = False
    os: str | None = None


_ROOT_KEYS = frozenset({"label", "path", "dot_only", "os"})


def _platform_names() -> frozenset[str]:
    from planeops.platform import discover_platforms

    return frozenset(p.name for p in discover_platforms())


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
        if path is None:
            raise ValueError(
                f"footprint.roots[{i}] path is null; YAML reads a bare ~ as "
                f'null, so home must be written path: "~"'
            )
        if not isinstance(path, str) or not path:
            raise ValueError(f"footprint.roots[{i}] path must be a non-empty string")
        dot_only = item.get("dot_only", False)
        if not isinstance(dot_only, bool):
            raise ValueError(f"footprint.roots[{i}] dot_only must be true or false")
        os_tag = item.get("os")
        if os_tag is not None and os_tag not in _platform_names():
            raise ValueError(
                f"footprint.roots[{i}] os must be one of "
                f"{sorted(_platform_names())} (got {os_tag!r})"
            )
        roots.append(
            FootprintRoot(label=label, path=path, dot_only=dot_only, os=os_tag)
        )
    return roots


def tool_key(name: str) -> str:
    """One identity per tool across conventions: `.ollama`, `Ollama`, and
    `ollama` merge. A name that is nothing but dots keeps its literal self."""
    stripped = name.lstrip(".").lower()
    return stripped or name


class FootprintAdapter:
    name = "footprint"
    domains: tuple[str, ...] = ("footprint",)

    def observe(self, ctx: Ctx) -> list[Observed]:
        home = ctx.platform.home()
        roots = [
            r
            for r in load_roots(ctx.repo_root)
            if r.os is None or r.os == ctx.platform.name
        ]
        # A configured root is a convention, not a tool: when home-dot and
        # xdg-config are both scanned, `.config` (and `.local`, which merely
        # holds the data/state roots) must not surface as tools themselves.
        bases = [resolve_path(r.path, home) for r in roots]
        merged: dict[str, list[dict[str, Any]]] = {}
        for root in roots:
            base = resolve_path(root.path, home)
            if not base.is_dir():
                continue  # the convention is simply not present here: quiet
            for child in sorted(base.iterdir()):
                if root.dot_only and not child.name.startswith("."):
                    continue
                if any(b == child or b.is_relative_to(child) for b in bases):
                    continue
                merged.setdefault(tool_key(child.name), []).append(
                    _footprint(root, child, home)
                )
        return [
            Observed(
                adapter=self.name,
                native_id=tool,
                facts={
                    "present": True,
                    "footprints": sorted(prints, key=lambda f: str(f["path"])),
                },
                version=None,
            )
            for tool, prints in sorted(merged.items())
        ]


def _footprint(root: FootprintRoot, child: Path, home: Path) -> dict[str, Any]:
    fp: dict[str, Any] = {
        "path": _display(child, home),
        "kind": "dir" if child.is_dir() else "file",
        "convention": root.label,
    }
    if child.is_symlink():
        fp["symlink"] = True
    return fp


def _display(path: Path, home: Path) -> str:
    """Home-relative for portability across hosts that share a layout."""
    try:
        return "~" + os.sep + str(path.relative_to(home))
    except ValueError:
        return str(path)


ADAPTER = FootprintAdapter()
