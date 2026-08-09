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

Debris is filtered by name before anything merges: `IGNORED_BY_DEFAULT`
skips OS artifacts, shell and editor state, backup copies, and the cache
dir, so discovery asks about tools, not about `.DS_Store`. `ignore:` extends
the list per instance and `ignore_defaults: false` drops it entirely;
registry-level `unmanaged` globs remain the id-level knob on top.

Children never need their own permissions (stat goes through the parent), so
a mode-000 credential dir observes like any other. A ROOT that cannot be
listed refuses loudly into the failed-scan alert, naming itself: silent
partial coverage would read as "covered everything".
"""

from __future__ import annotations

import fnmatch
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from planeops.config import section as instance_section
from planeops.core.contracts import Ctx, Observed
from planeops.core.paths import resolve_path
from planeops.core.schema import Entry, reject_unknown_keys


@dataclass(frozen=True, slots=True)
class FootprintRoot:
    label: str
    path: str
    dot_only: bool = False
    os: str | None = None


_ROOT_KEYS = frozenset({"label", "path", "dot_only", "os"})
_SECTION_KEYS = frozenset({"roots", "ignore", "ignore_defaults"})

# Debris, not tools: OS artifacts, shell and editor state, backup copies, and
# the cache dir (a convention that holds no intent). Matched against the
# on-disk child name with fnmatchcase, so behavior is identical on macOS and
# Linux. `ignore:` extends this list; `ignore_defaults: false` drops it.
IGNORED_BY_DEFAULT: tuple[str, ...] = (
    ".DS_Store",
    ".CFUserTextEncoding",
    ".Trash",
    ".localized",
    ".cache",
    ".viminfo",
    ".lesshst",
    "lesshst",
    ".zsh_sessions",
    ".bash_sessions",
    ".zcompdump*",
    "*_history",
    "*.bak",
    "*.backup",
    "*.old",
    "*~",
    "._*",
    "*.sw?",
    "cache",
)


def _section(repo_root: Path | None) -> dict[str, Any]:
    section = instance_section(repo_root, "footprint")
    reject_unknown_keys(section, _SECTION_KEYS, "footprint")
    return section


def load_ignore(repo_root: Path | None) -> tuple[str, ...]:
    """The name patterns this instance skips: the defaults (unless
    `ignore_defaults: false`) plus any `ignore:` additions."""
    section = _section(repo_root)
    defaults_on = section.get("ignore_defaults", True)
    if not isinstance(defaults_on, bool):
        raise ValueError("footprint.ignore_defaults must be true or false")
    extra = section.get("ignore") or []
    if not isinstance(extra, list) or not all(isinstance(p, str) and p for p in extra):
        raise ValueError("footprint.ignore must be a list of non-empty strings")
    return (IGNORED_BY_DEFAULT if defaults_on else ()) + tuple(extra)


def _platform_names() -> frozenset[str]:
    from planeops.platform import discover_platforms

    return frozenset(p.name for p in discover_platforms())


def load_roots(repo_root: Path | None) -> list[FootprintRoot]:
    """Read `footprint.roots` from instance.yaml. A missing file or section
    yields no roots (opt-in); a present but malformed root raises, landing in
    the snapshot's failed-scan alert, so a typo can never quietly mean
    "observe nothing"."""
    raw = _section(repo_root).get("roots")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(
            f"footprint.roots must be a list of mappings, got {type(raw).__name__}"
        )
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
    `ollama` merge. NFC first, so a name read from a normalizing filesystem
    matches the same text typed into the registry; casefold, so dotted-I and
    sharp-s spellings meet; one leading dot only, so `..foo` stays itself. A
    bare-dot name keeps its literal self."""
    normalized = unicodedata.normalize("NFC", name)
    stripped = normalized.removeprefix(".").casefold()
    return stripped or name


class FootprintAdapter:
    name = "footprint"
    domains: tuple[str, ...] = ("footprint",)

    def observe(self, ctx: Ctx) -> list[Observed]:
        home = ctx.platform.home()
        all_roots = load_roots(ctx.repo_root)
        roots = [r for r in all_roots if r.os is None or r.os == ctx.platform.name]
        # A configured root is a convention, not a tool, on EVERY system: an
        # os-tagged root keeps shielding its path where it is not scanned, so
        # `.config` and `.local` never surface as tools. Resolved, so a root
        # reached through a dotfiles symlink still shields its home-side name.
        bases = [resolve_path(r.path, home).resolve() for r in all_roots]
        ignore = load_ignore(ctx.repo_root)
        merged: dict[str, list[dict[str, Any]]] = {}
        for root in roots:
            base = resolve_path(root.path, home)
            try:
                # One guard around stat and listing both: a root planeops
                # cannot read would silently shrink coverage, so it refuses
                # loudly (into the failed-scan alert) with the fix. An absent
                # root stays quiet: the convention is simply not present.
                children = sorted(base.iterdir()) if base.is_dir() else None
            except PermissionError as exc:
                raise ValueError(
                    f"footprint root {root.label} ({base}) is not readable; "
                    "grant read access or remove the root"
                ) from exc
            if children is None:
                continue
            for child in children:
                if root.dot_only and not child.name.startswith("."):
                    continue
                if any(fnmatch.fnmatchcase(child.name, p) for p in ignore):
                    continue
                if any(b.is_relative_to(child.resolve()) for b in bases):
                    continue
                try:
                    trace = _footprint(root, child, home)
                except PermissionError as exc:
                    # Listable but not traversable (mode r--): child stats
                    # would lie, so the root refuses like an unreadable one.
                    raise ValueError(
                        f"footprint root {root.label} ({base}) is not "
                        "traversable; grant execute access or remove the root"
                    ) from exc
                if trace is None:
                    continue  # vanished between the listing and the stat
                merged.setdefault(tool_key(child.name), []).append(trace)
        owners = _attributions(ctx.entries, self.name)
        out: list[Observed] = []
        for tool, prints in sorted(merged.items()):
            facts: dict[str, Any] = {
                "present": True,
                "footprints": sorted(prints, key=lambda f: str(f["path"])),
            }
            if tool in owners:
                facts["governed_by"] = owners[tool]
            out.append(
                Observed(adapter=self.name, native_id=tool, facts=facts, version=None)
            )
        return out


def _attributions(entries: tuple[Entry, ...], self_name: str) -> dict[str, str]:
    """tool key -> the id of an entry from ANOTHER adapter whose native id
    names the same tool: `pkg-brew/gh` owns the `~/.config/gh` trace, so the
    trace is evidence for a decision already made, not a new question. First
    match by sorted entry id, so attribution never depends on registry file
    order."""
    owners: dict[str, str] = {}
    for entry in sorted(entries, key=lambda e: e.id):
        if entry.adapter == self_name:
            continue
        owners.setdefault(tool_key(entry.native_id), entry.id)
    return owners


def _footprint(root: FootprintRoot, child: Path, home: Path) -> dict[str, Any] | None:
    try:
        child.lstat()
    except FileNotFoundError:
        return None  # deleted since the listing; nothing to record
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
        rel = path.relative_to(home)
    except ValueError:
        return str(path)
    return "~" if str(rel) == "." else "~" + os.sep + str(rel)


ADAPTER = FootprintAdapter()
