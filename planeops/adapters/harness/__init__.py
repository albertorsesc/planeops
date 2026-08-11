"""The harness adapter: code plugged into an AI harness.

A harness loads code the human plugged into it, and some of that code RUNS on
its own: a hook fires on every tool call, on session start, on stop. Nothing
else on the machine watches that surface, so an undeclared one is exactly the
"runs code, nobody declared it" case the triage already alerts on.

Profiles are configuration, `{label, path}` under `harness.profiles` in
instance.yaml. The layout behind a label (which file holds the settings, and
how that file's schema names its hooks) is one harness leaf's business, under
`harnesses/`, discovered like every other seam. This module therefore names
no tool: it resolves profiles, asks the leaf for hooks, and turns them into
observations. No section means no scan.

A hook's identity is its kind, its event, and the script it runs, because
that is what a human recognises and what stays stable when a matcher is
edited. The command STRING is never recorded: it is a shell line that can
carry a token, and the script path is the identity anyway. `present` means
the hook will actually run: declared, and its script resolves. A hook whose
script is gone is wired but broken, which is the same violation as any
active asset that is not there.
"""

from __future__ import annotations

import hashlib
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from planeops.config import section as instance_section
from planeops.core.contracts import Ctx, Observed
from planeops.core.paths import resolve_path
from planeops.core.schema import reject_unknown_keys

# Suffixes that name a script a command runs. A command may invoke a runtime
# and pass the script as an argument (`node plug/beta.cjs`), and such a file
# is deliberately not executable, so resolvability is the test, never the
# executable bit.
SCRIPT_SUFFIXES = frozenset(
    {".sh", ".bash", ".zsh", ".py", ".rb", ".pl", ".js", ".cjs", ".mjs", ".ts"}
)

_PROFILE_KEYS = frozenset({"label", "path"})
_SECTION_KEYS = frozenset({"profiles"})


# A hook reader: given one harness's parsed settings, yields (event, command)
# for every hook it declares. Each leaf owns its own schema.
@runtime_checkable
class KnownHarnessProto(Protocol):
    label: str
    config: str  # settings file, relative to the profile's path

    def hooks(self, data: dict[str, Any]) -> list[tuple[str, str]]: ...


@dataclass(frozen=True, slots=True)
class KnownHarness:
    label: str
    config: str
    hooks: Any  # Callable[[dict], list[tuple[str, str]]]


@dataclass(frozen=True, slots=True)
class HarnessProfile:
    label: str
    path: str


def discover_harnesses() -> dict[str, KnownHarness]:
    """Every `planeops.adapters.harness.harnesses.<mod>` exposing a `HARNESS`."""
    import planeops.adapters.harness.harnesses as pkg
    from planeops.core.discovery import discover

    return discover(pkg, "HARNESS", KnownHarness, key="label")


def load_profiles(repo_root: Path | None) -> list[HarnessProfile]:
    """Read `harness.profiles` from instance.yaml. A missing file or section
    yields none (opt-in); a present but malformed profile raises, landing in
    the snapshot's failed-scan alert, so a typo can never quietly mean
    "observe nothing"."""
    section = instance_section(repo_root, "harness")
    reject_unknown_keys(section, _SECTION_KEYS, "harness")
    raw = section.get("profiles")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(
            f"harness.profiles must be a list of mappings, got {type(raw).__name__}"
        )
    out: list[HarnessProfile] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"harness.profiles[{i}] must be a mapping, got {item!r}")
        reject_unknown_keys(item, _PROFILE_KEYS, f"harness.profiles[{i}]")
        label, path = item.get("label"), item.get("path")
        if not isinstance(label, str) or not label:
            raise ValueError(f"harness.profiles[{i}] label must be a non-empty string")
        if not isinstance(path, str) or not path:
            raise ValueError(f"harness.profiles[{i}] path must be a non-empty string")
        out.append(HarnessProfile(label=label, path=path))
    return out


def script_of(command: str) -> Path | None:
    """The file a command runs, when it names one. A command is a shell line:
    the script may be the first word or an argument to a runtime, so the
    first token that looks like a script wins, and a command that names none
    (an inline shell snippet) yields nothing to resolve."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    for part in parts:
        if part.startswith("-"):
            continue
        if Path(part).suffix in SCRIPT_SUFFIXES:
            return Path(part).expanduser()
    return None


def _slug(command: str, script: Path | None) -> str:
    """The readable half of a hook's id: its script's stem, or a short digest
    of the command when it runs no script. Deterministic either way."""
    if script is not None:
        return script.stem
    return hashlib.sha256(command.encode()).hexdigest()[:8]


def _display(path: Path, home: Path) -> str:
    try:
        return "~/" + str(path.relative_to(home))
    except ValueError:
        return str(path)


class HarnessAdapter:
    name = "harness"
    domains: tuple[str, ...] = ("hook",)

    def __init__(self, harnesses: dict[str, KnownHarness] | None = None):
        self._harnesses = harnesses

    def _known(self) -> dict[str, KnownHarness]:
        return self._harnesses if self._harnesses is not None else discover_harnesses()

    def observe(self, ctx: Ctx) -> list[Observed]:
        home = ctx.platform.home()
        known = self._known()
        merged: dict[str, dict[str, Any]] = {}
        # The command each id came from, kept OUT of the facts: a shell line
        # can carry a token, and only collision detection needs it.
        commands: dict[str, str] = {}
        for profile in load_profiles(ctx.repo_root):
            harness = known.get(profile.label)
            if harness is None:
                raise ValueError(
                    f"harness.profiles names {profile.label!r}, which no harness "
                    f"leaf claims; known: {sorted(known) or 'none'}"
                )
            base = resolve_path(profile.path, home)
            config = base / harness.config
            if not config.is_file():
                continue  # this profile is simply not on the machine: quiet
            data = _read(config)
            for event, command in harness.hooks(data):
                _merge(merged, commands, profile, event, command, home)
        return [
            Observed(adapter=self.name, native_id=native, facts=facts, version=None)
            for native, facts in sorted(merged.items())
        ]


def _read(config: Path) -> dict[str, Any]:
    """The harness's own settings, parsed. A settings file that is present but
    unreadable is a coverage hole, so it refuses rather than observing
    nothing."""
    import json

    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{config} is not readable settings: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{config} is not a settings mapping")
    return data


def _merge(
    merged: dict[str, dict[str, Any]],
    commands: dict[str, str],
    profile: HarnessProfile,
    event: str,
    command: str,
    home: Path,
) -> None:
    """One hook, folded in under its identity. The same hook wired in several
    profiles is one thing that runs, listed against each profile that wires
    it, the way a server wired into several clients is one server."""
    script = script_of(command)
    native = f"hook/{event}/{_slug(command, script)}"
    if commands.get(native, command) != command:
        # Two different commands share an event and a script name; keep both
        # distinguishable rather than letting one swallow the other.
        native = f"{native}-{hashlib.sha256(command.encode()).hexdigest()[:6]}"
    commands.setdefault(native, command)
    entry = merged.setdefault(
        native,
        {
            "present": script is None or script.exists(),
            "kind": "hook",
            "always_on": True,
            "event": event,
            # The tool, then the config dirs of that tool that wire this hook.
            # A label names the harness, and one machine commonly runs several
            # profiles of the same harness, so the PATH is what tells them
            # apart and what a human needs in order to go edit the right one.
            "harness": profile.label,
            "profiles": [],
        },
    )
    if script is not None:
        entry["runs"] = _display(script, home)
    entry["profiles"].append(_display(resolve_path(profile.path, home), home))


ADAPTER = HarnessAdapter()
