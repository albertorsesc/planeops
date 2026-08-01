"""launchd scheduler backend (macOS): a LaunchAgent plist that runs `plane reconcile`
at login and on an interval (not a fixed clock time, which would miss if the machine
is asleep then).

Generates the plist and declares a `launchd/<label>` entry; `plane apply` loads it via
the launchd adapter. The current PATH is baked into the job so the scheduled reconcile
sees the same tools the user does (else adapters that shell out, npm/brew/ollama, would
find nothing under launchd's minimal env and drift would lie).
"""

from __future__ import annotations

import plistlib
from pathlib import Path

from planeops.schedulers import ScheduledJob

LABEL = "ai.planeops.reconcile"


class LaunchdScheduler:
    name = "launchd"
    sys_platforms: tuple[str, ...] = ("darwin",)

    def build(
        self,
        home: Path,
        *,
        plane: str,
        path_env: str,
        interval: int,
        login: bool,
        off: bool,
    ) -> ScheduledJob:
        log_dir = home / "Library" / "Logs" / "planeops-reconcile"
        plist: dict[str, object] = {
            "Label": LABEL,
            "ProgramArguments": [plane, "reconcile"],
            "StartInterval": interval,  # every N seconds, robust to sleep/off
            "EnvironmentVariables": {"PATH": path_env, "HOME": str(home)},
            "StandardOutPath": str(log_dir / "launchd.out.log"),
            "StandardErrorPath": str(log_dir / "launchd.err.log"),
        }
        if login:
            plist["RunAtLoad"] = True
        plist_path = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        entry = {
            "id": f"launchd/{LABEL}",
            "adapter": "launchd",
            "domain": "service",
            "lifecycle": "retired" if off else "active",
            # A dead reconcile heartbeat rots every other signal, so escalate: the
            # adapter sets facts.drifted when the agent is unloaded, and `alert` routes
            # that to an alert rather than a quiet report.
            "tolerance": "alert",
            "intent": "planeops ambient reconcile, managed by `plane schedule`",
        }
        verb = "unload" if off else "load"
        return ScheduledJob(
            files={plist_path: plistlib.dumps(plist).decode()},
            entries=[entry],
            hint=f"scheduled {'off' if off else 'on'}; run `plane apply` to {verb} it",
        )


SCHEDULER = LaunchdScheduler()
