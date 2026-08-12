"""launchd adapter (darwin services).

observe reports which user LaunchAgents exist and whether they are loaded, so
drift catches a service listed `retired` that is still loaded. plan/execute
converge that: bootout a retired-but-loaded service, bootstrap an active-but-
unloaded one. The engine owns confirmation, so execute runs only per confirmed
Change.

OS access goes through one injected seam (`run`) plus `ctx.platform.home()`, so
the adapter is testable against recorded fixtures and never shells out from the
core.
"""

from __future__ import annotations

import os
import plistlib
from pathlib import Path
from typing import Any

from planeops._run import Runner, default_run
from planeops.core.contracts import Change, Ctx, Observed, Result
from planeops.core.schema import ABSENT_LIFECYCLES, Entry, Lifecycle


def parse_launchctl_list(text: str) -> dict[str, int | None]:
    """Map label -> pid (None when loaded but not running). Input is the
    `PID<TAB>Status<TAB>Label` table `launchctl list` prints."""
    jobs: dict[str, int | None] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] == "PID":
            continue
        pid_str, _status, label = parts
        jobs[label] = (
            int(pid_str)
            if pid_str.strip().lstrip("-").isdigit() and pid_str != "-"
            else None
        )
    return jobs


def read_plist(path: Path) -> dict[str, Any]:
    """Extract the fields the adapter reports. Unreadable plists degrade to the
    filename as label rather than crashing the scan."""
    try:
        with path.open("rb") as fh:
            data = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return {
            "label": path.stem,
            "keepalive": False,
            "run_at_load": False,
            "scheduled": False,
            "logs": [],
        }
    return {
        "label": data.get("Label", path.stem),
        "keepalive": bool(data.get("KeepAlive")),
        "run_at_load": bool(data.get("RunAtLoad")),
        # A plist with an interval/calendar trigger must be loaded to ever fire.
        "scheduled": bool(
            data.get("StartInterval") or data.get("StartCalendarInterval")
        ),
        # The plist declares where the service logs; carried so a seeded
        # manifest knows without hand-hunting.
        "logs": [
            str(p)
            for p in (data.get("StandardOutPath"), data.get("StandardErrorPath"))
            if p
        ],
    }


class LaunchdAdapter:
    name = "launchd"
    domains: tuple[str, ...] = ("service",)
    # Converge order: services load LAST, against complete config and secrets.
    default_phase = 6
    # Service ops are quick; a bounded ceiling keeps a hung launchctl from
    # wedging the whole apply run (unlike unbounded package installs).
    EXECUTE_TIMEOUT: float | None = 300

    def __init__(self, run: Runner | None = None, agents_dir: Path | None = None):
        self._run = run or default_run
        self._agents_dir_override = agents_dir

    def _agents_dir(self, ctx: Ctx) -> Path:
        if self._agents_dir_override is not None:
            return self._agents_dir_override
        return ctx.platform.home() / "Library" / "LaunchAgents"

    def observe(self, ctx: Ctx) -> list[Observed]:
        loaded = parse_launchctl_list(self._run(["launchctl", "list"]).out)
        agents_dir = self._agents_dir(ctx)
        if not agents_dir.is_dir():
            return []

        out: list[Observed] = []
        for plist_path in sorted(agents_dir.glob("*.plist")):
            meta = read_plist(plist_path)
            label = meta["label"]
            is_loaded = label in loaded
            pid = loaded.get(label)
            # A plist whose own definition means it to stay up (load at login, keep
            # alive, or fire on a schedule) but that is not loaded has drifted from that
            # intent: the dead-heartbeat signal. An on-demand agent (none of those) is
            # fine unloaded. Triage routes `drifted` by the entry's tolerance, so a
            # reconcile schedule marks it `alert` while a plain service reports it.
            wants_loaded = meta["run_at_load"] or meta["keepalive"] or meta["scheduled"]
            out.append(
                Observed.of(
                    self.name,
                    label,
                    drifted=bool(wants_loaded and not is_loaded),
                    # Drift's ungoverned pass reads this: the agent will run code
                    # (login/keepalive/interval) even if it is not loaded right
                    # now, so undeclared it must alert.
                    always_on=bool(wants_loaded),
                    # Semantic presence for drift's retired check: a service is
                    # "present" when loaded, not when its file exists, so
                    # retired+booted-out+file-on-disk reads as converged.
                    present=is_loaded,
                    detail={
                        "loaded": is_loaded,
                        "running": is_loaded and pid is not None,
                        "pid": pid,
                        "keepalive": meta["keepalive"],
                        "run_at_load": meta["run_at_load"],
                        "plist_path": str(plist_path),
                        **({"logs": meta["logs"]} if meta["logs"] else {}),
                    },
                )
            )
        return out

    def plan(self, entry: Entry, obs: Observed | None, ctx: Ctx) -> list[Change]:
        if obs is None:
            return []  # nothing observed on disk to load or unload
        facts = obs.facts
        label = obs.native_id
        plist_path = facts.get("plist_path")

        if entry.lifecycle in ABSENT_LIFECYCLES:
            if not facts.get("loaded"):
                return []  # already absent as desired
            purge = entry.lifecycle is Lifecycle.purge
            tail = " and delete its plist" if purge else ""
            pid = facts.get("pid")
            state = f"pid {pid}" if pid is not None else "loaded, not running"
            return [
                Change(
                    entry_id=entry.id,
                    kind="remove",
                    diff=f"launchd: bootout {label}{tail} ({state})",
                    action={
                        "op": "bootout",
                        "label": label,
                        "plist_path": plist_path,
                        "delete_plist": purge,
                    },
                )
            ]

        if entry.lifecycle is Lifecycle.parked:
            # Parked means keep-as-is: on disk is enough, loaded or not.
            return []

        if not facts.get("loaded"):
            return [
                Change(
                    entry_id=entry.id,
                    kind="configure",
                    diff=(
                        f"launchd: bootstrap {label} from {plist_path} "
                        "(present but not loaded)"
                    ),
                    action={
                        "op": "bootstrap",
                        "label": label,
                        "plist_path": plist_path,
                    },
                )
            ]
        return []

    def execute(self, change: Change, ctx: Ctx) -> Result:
        action = change.action
        op = action.get("op")
        label = action.get("label", "")
        domain = f"gui/{os.getuid()}"

        if op == "bootout":
            res = self._run(
                ["launchctl", "bootout", f"{domain}/{label}"],
                timeout=self.EXECUTE_TIMEOUT,
            )
            if res.code != 0:
                return Result(
                    ok=False,
                    detail=f"bootout {label} failed: {res.err.strip() or res.code}",
                )
            if action.get("delete_plist") and action.get("plist_path"):
                try:
                    Path(action["plist_path"]).unlink()
                except OSError as exc:
                    return Result(
                        ok=False,
                        detail=f"booted out {label} but plist delete failed: {exc}",
                    )
            return Result(ok=True, detail=f"booted out {label}")

        if op == "bootstrap":
            res = self._run(
                ["launchctl", "bootstrap", domain, action.get("plist_path", "")],
                timeout=self.EXECUTE_TIMEOUT,
            )
            if res.code != 0:
                return Result(
                    ok=False,
                    detail=f"bootstrap {label} failed: {res.err.strip() or res.code}",
                )
            return Result(ok=True, detail=f"bootstrapped {label}")

        return Result(ok=False, detail=f"unknown launchd op {op!r}")


ADAPTER = LaunchdAdapter()
