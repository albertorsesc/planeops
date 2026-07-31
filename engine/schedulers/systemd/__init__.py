"""systemd scheduler backend (Linux): a `--user` .timer + .service running `plane
reconcile` at boot/login and on an interval.

Generates the paired units and declares a `systemd/<unit>.timer` entry (the on/off
switch, governed via drift/apply through the systemd adapter). The oneshot .service the
timer triggers is bundled but declared `unmanaged` (it exists, but is timer-driven, not
enabled on its own, so it shouldn't read as ungoverned drift). PATH is baked in, same
reason as launchd.
"""

from __future__ import annotations

from pathlib import Path

from engine.schedulers import ScheduledJob

UNIT = "planeops-reconcile"


class SystemdScheduler:
    name = "systemd"
    sys_platforms: tuple[str, ...] = ("linux",)

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
        # The unit files are plain-text concatenation: a newline inside an
        # interpolated value would land as a new directive line (e.g. an
        # ExecStartPre= injected through $PATH). No legitimate PATH or binary
        # path contains one; refuse loudly rather than write a poisoned unit.
        for label, value in (("plane path", plane), ("PATH", path_env)):
            if "\n" in value or "\r" in value:
                raise ValueError(
                    f"{label} contains a newline; refusing to write a unit"
                )
        user_dir = home / ".config" / "systemd" / "user"
        service = (
            "[Unit]\nDescription=planeops ambient reconcile (observe+drift)\n\n"
            f"[Service]\nType=oneshot\nEnvironment=PATH={path_env}\n"
            f"ExecStart={plane} reconcile\n"
        )
        # OnUnitActiveSec = every N since the last run, but it is relative to
        # the SERVICE's last activation, so it alone never fires on a fresh
        # enable. OnActiveSec (relative to the TIMER's activation) schedules
        # the first run at enable time; OnBootSec adds the login/boot trigger.
        # No Persistent=: it only affects OnCalendar timers, a no-op here.
        timer = (
            "[Unit]\nDescription=planeops ambient reconcile schedule\n\n"
            f"[Timer]\nOnActiveSec={interval}s\nOnUnitActiveSec={interval}s\n"
            + ("OnBootSec=2min\n" if login else "")
            + "\n[Install]\nWantedBy=timers.target\n"
        )
        entry = {
            "id": f"systemd/{UNIT}.timer",
            "adapter": "systemd",
            "domain": "service",
            "lifecycle": "retired" if off else "active",
            # A dead reconcile heartbeat rots every other signal, so escalate: the
            # adapter sets facts.drifted when the timer is disabled/inactive, and
            # `alert` routes that to an alert rather than a quiet report.
            "tolerance": "alert",
            "intent": "planeops ambient reconcile schedule (via `plane schedule`)",
        }
        verb = "unload" if off else "load"
        return ScheduledJob(
            files={
                user_dir / f"{UNIT}.service": service,
                user_dir / f"{UNIT}.timer": timer,
            },
            entries=[entry],
            globs=[{"glob": f"systemd/{UNIT}.service"}],  # timer-driven, ungoverned
            hint=f"scheduled {'off' if off else 'on'}; run `plane apply` to {verb} it",
        )


SCHEDULER = SystemdScheduler()
