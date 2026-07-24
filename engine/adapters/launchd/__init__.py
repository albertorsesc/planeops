"""launchd adapter (darwin services). Observe-only in M1: it reports which
user LaunchAgents exist and whether they are loaded/running, so DRIFT can catch
the founding failure, a service listed `retired` that is still loaded.

plan/execute (bootout/bootstrap, plist install/remove) land in M2; until then
this is a plain observe-only Adapter and `plane apply` never touches it.

OS access goes through one injected seam (`run`, a launchctl command runner) and
`ctx.platform.home()`, so the adapter is testable against recorded fixtures and
never hard-codes a path or shells out from inside the core.
"""

from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path
from typing import Callable

from engine.core.contracts import Ctx, Observed

Runner = Callable[[list[str]], str]


def _default_run(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout


def parse_launchctl_list(text: str) -> dict[str, int | None]:
    """Map label -> pid (None when loaded but not running). Input is the
    `PID<TAB>Status<TAB>Label` table `launchctl list` prints."""
    jobs: dict[str, int | None] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] == "PID":
            continue
        pid_str, _status, label = parts
        jobs[label] = int(pid_str) if pid_str.strip().lstrip("-").isdigit() and pid_str != "-" else None
    return jobs


def read_plist(path: Path) -> dict:
    """Extract the fields the adapter reports. Unreadable plists degrade to the
    filename as label rather than crashing the scan."""
    try:
        with path.open("rb") as fh:
            data = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return {"label": path.stem, "keepalive": False, "run_at_load": False}
    return {
        "label": data.get("Label", path.stem),
        "keepalive": bool(data.get("KeepAlive")),
        "run_at_load": bool(data.get("RunAtLoad")),
    }


class LaunchdAdapter:
    name = "launchd"
    domains: tuple[str, ...] = ("service",)

    def __init__(self, run: Runner | None = None, agents_dir: Path | None = None):
        self._run = run or _default_run
        self._agents_dir_override = agents_dir

    def _agents_dir(self, ctx: Ctx) -> Path:
        if self._agents_dir_override is not None:
            return self._agents_dir_override
        return ctx.platform.home() / "Library" / "LaunchAgents"

    def observe(self, ctx: Ctx) -> list[Observed]:
        loaded = parse_launchctl_list(self._run(["launchctl", "list"]))
        agents_dir = self._agents_dir(ctx)
        if not agents_dir.is_dir():
            return []

        out: list[Observed] = []
        for plist_path in sorted(agents_dir.glob("*.plist")):
            meta = read_plist(plist_path)
            label = meta["label"]
            is_loaded = label in loaded
            pid = loaded.get(label)
            out.append(
                Observed(
                    adapter=self.name,
                    native_id=label,
                    facts={
                        "loaded": is_loaded,
                        "running": is_loaded and pid is not None,
                        "pid": pid,
                        "keepalive": meta["keepalive"],
                        "run_at_load": meta["run_at_load"],
                        "plist_path": str(plist_path),
                    },
                )
            )
        return out


ADAPTER = LaunchdAdapter()
