"""Scheduler seam: one backend per OS behind the `Scheduler` contract.

`plane schedule` sets up the ambient reconcile, an OS-native periodic job that runs
`plane reconcile`. Each OS module under `planeops/schedulers/` exposes a module-level
`SCHEDULER` declaring the `sys.platform` prefixes it serves; `current_scheduler()`
selects the host's by scanning, the same package-scan / no-central-list discipline
adapters, importers, and platforms use. Adding an OS is dropping a module in.

A backend is pure: `build(...)` returns a `ScheduledJob` (the files to write and the
registry entry to declare); it neither writes files nor loads the job. Writing is the
CLI's job; loading is `plane apply`'s, through the launchd/systemd adapter and its
confirmation gate, so scheduling stays on the one mutation path.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    """What a backend produces: the OS job files to write, the registry entries to
    declare (the reconcile job, governed via drift/apply), and unmanaged globs for
    bundled units that exist but aren't governed on their own (e.g. a timer's paired
    service). `hint` is the one-line next step the CLI prints."""

    files: dict[Path, str]
    entries: list[dict[str, Any]]
    hint: str
    globs: list[dict[str, str]] = field(default_factory=list)


@runtime_checkable
class Scheduler(Protocol):
    name: str
    sys_platforms: tuple[str, ...]

    def build(
        self,
        home: Path,
        *,
        plane: str,
        path_env: str,
        interval: int,
        login: bool,
        off: bool,
    ) -> ScheduledJob: ...


def discover_schedulers() -> list[Scheduler]:
    """Every `planeops.schedulers.<os>` exposing a module-level `SCHEDULER`."""
    import planeops.schedulers
    from planeops.core.discovery import discover

    found = discover(
        planeops.schedulers,
        "SCHEDULER",
        Scheduler,  # type: ignore[type-abstract]  # isinstance-only, see discover()
    )
    return list(found.values())


def current_scheduler() -> Scheduler:
    """The scheduler backend for the host OS, selected by discovery."""
    for scheduler in discover_schedulers():
        if any(sys.platform.startswith(s) for s in scheduler.sys_platforms):
            return scheduler
    raise NotImplementedError(f"no scheduler backend for {sys.platform!r} yet")
