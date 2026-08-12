"""systemd adapter (Linux user services).

The Linux parity to the launchd adapter: observe reports which user units exist and
whether they are enabled and active, so drift catches a `retired` service still
enabled/running. plan/execute converge that, `enable --now` an active-but-off unit,
`disable --now` a retired-but-on one, mirroring launchd's bootstrap/bootout. The
engine owns confirmation, so execute runs only per confirmed Change.

Two axes, unlike launchd's single "loaded": systemd separates ENABLED (starts on
login, `is-enabled`) from ACTIVE (running now, `is-active`); each is read from the
status WORD, one unit per call, because the exit code alone conflates `static` and
`masked` with enabled/disabled. A unit is a unit: `.service` and `.timer` are
observed and converged identically (is-enabled/is-active, enable/disable apply to
both), so a scheduled `.timer` is governed with no per-type branching. User unit
files live in `~/.config/systemd/user/`.
OS access goes through the injected `run` seam plus `ctx.platform.home()`, so the
adapter is testable against fixtures and, where no `systemd --user` session exists
(e.g. macOS), observes nothing rather than crashing.
"""

from __future__ import annotations

from pathlib import Path

from planeops._run import Runner, default_run
from planeops.core.contracts import Change, Ctx, Observed, Result
from planeops.core.schema import ABSENT_LIFECYCLES, Entry, Lifecycle


class SystemdAdapter:
    name = "systemd"
    domains: tuple[str, ...] = ("service",)
    # Converge order: services load LAST, against complete config and secrets.
    default_phase = 6
    # Unit types this adapter governs, as data, not a branch. is-enabled/is-active and
    # enable/disable are type-agnostic, so a `.timer` observes and converges exactly
    # like a `.service`; add a type here and the whole adapter picks it up.
    UNIT_TYPES: tuple[str, ...] = ("service", "timer")
    # Unit ops are quick; a bounded ceiling keeps a hung systemctl (e.g. a unit
    # stuck deactivating under --now) from wedging the whole apply run.
    EXECUTE_TIMEOUT: float | None = 300

    def __init__(self, run: Runner | None = None, units_dir: Path | None = None):
        self._run = run or default_run
        self._units_dir_override = units_dir

    def _units_dir(self, ctx: Ctx) -> Path:
        if self._units_dir_override is not None:
            return self._units_dir_override
        return ctx.platform.home() / ".config" / "systemd" / "user"

    def observe(self, ctx: Ctx) -> list[Observed]:
        units_dir = self._units_dir(ctx)
        if not units_dir.is_dir():
            return []
        # systemctl absent entirely (macOS, a systemd-less box): not an error,
        # nothing to observe. But systemctl PRESENT with unit files on disk and
        # an unreachable user bus must be loud: observing zero units silently
        # made the snapshot lie (the classic case is a container/CI/SSH session
        # without XDG_RUNTIME_DIR).
        probe = self._run(["systemctl", "--user", "list-units", "--no-legend"])
        if probe.code != 0:
            has_units = any(
                unit_path.exists()
                for t in self.UNIT_TYPES
                for unit_path in units_dir.glob(f"*.{t}")
            )
            if probe.code == 127 or not has_units:
                return []
            raise ValueError(
                f"systemctl --user is unreachable ({probe.err.strip()[:120]}) "
                f"while user units exist in {units_dir}; no session bus? "
                'try XDG_RUNTIME_DIR=/run/user/"$(id -u)"'
            )

        out: list[Observed] = []
        paths = sorted(p for t in self.UNIT_TYPES for p in units_dir.glob(f"*.{t}"))
        for unit_path in paths:
            if unit_path.stem.endswith("@"):
                continue  # a template (foo@.service / foo@.timer), not a runnable unit
            unit = unit_path.name
            enabled_word = self._state(unit, "is-enabled")
            enabled = enabled_word in ("enabled", "enabled-runtime")
            active = self._state(unit, "is-active") == "active"
            # A unit whose own definition means it to run but doesn't has drifted:
            # installable yet `disabled`, or enabled yet not active. A `static` unit (no
            # [Install]) reads neither, so a timer-driven oneshot stays silent between
            # runs. Triage routes `drifted` by tolerance, so a reconcile timer marks it
            # `alert` (dead heartbeat) while a plain unit reports it.
            drifted = enabled_word == "disabled" or (enabled and not active)
            out.append(
                Observed.of(
                    self.name,
                    unit,
                    drifted=drifted,
                    # Drift's ungoverned pass reads this: an enabled unit starts
                    # at login, so undeclared it must alert.
                    always_on=enabled,
                    # Semantic presence for drift's retired check: a unit is
                    # "present" when it will run or is running, not when its
                    # file exists on disk.
                    present=enabled or active,
                    detail={
                        "enabled": enabled,
                        "active": active,
                        # Where the unit's output goes; carried so a seeded
                        # manifest knows without hand-hunting.
                        "logs": [f"journalctl --user -u {unit}"],
                        "unit_path": str(unit_path),
                    },
                )
            )
        return out

    def _state(self, unit: str, check: str) -> str:
        # The status WORD from is-enabled/is-active, one unit per call. The exit code
        # alone is ambiguous: `static` and `masked` also exit 0/non-0 in ways that
        # would read as enabled/disabled, so decide on the word instead.
        return self._run(["systemctl", "--user", check, unit]).out.strip()

    def plan(self, entry: Entry, obs: Observed | None, ctx: Ctx) -> list[Change]:
        if obs is None:
            return []  # no unit file observed to enable or disable
        facts = obs.facts
        unit = obs.native_id
        unit_path = facts.get("unit_path")
        enabled = bool(facts.get("enabled"))
        active = bool(facts.get("active"))

        if entry.lifecycle in ABSENT_LIFECYCLES:
            if not enabled and not active:
                return []  # already off as desired
            purge = entry.lifecycle is Lifecycle.purge
            tail = " and delete its unit file" if purge else ""
            return [
                Change(
                    entry_id=entry.id,
                    kind="remove",
                    diff=f"systemd: disable --now {unit}{tail} "
                    f"(enabled={enabled}, active={active})",
                    action={
                        "op": "disable",
                        "unit": unit,
                        "unit_path": unit_path,
                        "delete_unit": purge,
                    },
                )
            ]

        if entry.lifecycle is Lifecycle.parked:
            # Parked means keep-as-is: on disk is enough, enabled or not.
            return []

        if not (enabled and active):
            return [
                Change(
                    entry_id=entry.id,
                    kind="configure",
                    diff=f"systemd: enable --now {unit} "
                    f"(enabled={enabled}, active={active})",
                    action={"op": "enable", "unit": unit, "unit_path": unit_path},
                )
            ]
        return []

    def execute(self, change: Change, ctx: Ctx) -> Result:
        action = change.action
        op = action.get("op")
        unit = action.get("unit", "")

        if op == "enable":
            # Pick up a freshly written unit file, then enable + start in one call.
            self._run(["systemctl", "--user", "daemon-reload"])
            res = self._run(
                ["systemctl", "--user", "enable", "--now", unit],
                timeout=self.EXECUTE_TIMEOUT,
            )
            if res.code != 0:
                return Result(
                    ok=False,
                    detail=f"enable {unit} failed: {res.err.strip() or res.code}",
                )
            return Result(ok=True, detail=f"enabled + started {unit}")

        if op == "disable":
            res = self._run(
                ["systemctl", "--user", "disable", "--now", unit],
                timeout=self.EXECUTE_TIMEOUT,
            )
            if res.code != 0:
                return Result(
                    ok=False,
                    detail=f"disable {unit} failed: {res.err.strip() or res.code}",
                )
            if action.get("delete_unit") and action.get("unit_path"):
                try:
                    Path(action["unit_path"]).unlink()
                except OSError as exc:
                    return Result(
                        ok=False,
                        detail=f"disabled {unit} but unit-file delete failed: {exc}",
                    )
                self._run(["systemctl", "--user", "daemon-reload"])
            return Result(ok=True, detail=f"disabled + stopped {unit}")

        return Result(ok=False, detail=f"unknown systemd op {op!r}")


ADAPTER = SystemdAdapter()
