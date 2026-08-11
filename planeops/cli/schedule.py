"""`plane schedule`: set up the ambient reconcile timer (then `plane apply`
loads it). The per-OS backend is discovered; this module owns the CLI wiring,
the confirm gate, and the interval grammar."""

from __future__ import annotations

import argparse


def _parse_every(value: str) -> int:
    """`6h`/`30m`/`90s` -> seconds. Rejects anything else."""
    units = {"h": 3600, "m": 60, "s": 1}
    unit, number = value[-1:], value[:-1]
    if unit not in units or not number.isdigit() or int(number) <= 0:
        raise ValueError
    return int(number) * units[unit]


def _cmd(args: argparse.Namespace) -> int:
    import os
    import shutil

    from planeops.cli.instance import instance_root
    from planeops.core.prompt import ask
    from planeops.core.statefile import atomic_write
    from planeops.importers import render_proposal
    from planeops.platform import current_platform
    from planeops.providers import ui, yaml
    from planeops.schedulers import current_scheduler

    try:
        interval = _parse_every(args.every)
    except ValueError:
        ui.err(f"--every must be like 6h/30m/90s (got {args.every!r})")
        return 1

    home = current_platform().home()
    which = shutil.which("plane")
    plane = which or str(home / ".local" / "bin" / "plane")
    if which is None and not (home / ".local" / "bin" / "plane").exists():
        # The job would silently fail at fire time; say so at schedule time.
        ui.warn(
            f"warning: plane is not on PATH and {plane} does not exist; the "
            "scheduled job may fail until planeops is installed there",
            stderr=True,
        )
    scheduler = current_scheduler()  # NotImplementedError -> main()'s handler

    try:
        job = scheduler.build(
            home,
            plane=plane,
            path_env=os.environ.get("PATH", ""),
            interval=interval,
            login=not args.no_login,
            off=args.off,
        )
    except ValueError as exc:  # a backend refusing an unsafe value (not central:
        ui.err(str(exc))  # ValueError is too broad to catch there)
        return 1

    repo = instance_root(args)
    # schedule writes machine state (job files + a registry entry): show what it
    # will write and confirm, the same posture as `import --write`. No readable
    # stdin and no --yes: write nothing.
    ui.title("schedule will write:")
    for path in job.files:
        ui.line(f"  {path}")
    ui.line(f"  {repo / 'registry' / 'schedule.yaml'} declaring:")
    entry_doc: dict[str, object] = {"entries": job.entries}
    ui.line("    " + yaml.dump(entry_doc).rstrip().replace("\n", "\n    "))
    if not args.yes:
        # Nobody to ask reads as an empty line, which the `(y/N)` below
        # declines: writing a timer is never the default.
        answer = ask("proceed? (y/N) ") or ""
        if answer.strip().lower()[:1] != "y":
            ui.note("not written (use --yes to write non-interactively)")
            return 0

    for path, content in job.files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, content)
        ui.good(f"wrote {path}")

    schedule_yaml = repo / "registry" / "schedule.yaml"
    schedule_yaml.parent.mkdir(parents=True, exist_ok=True)
    text = render_proposal(list(job.entries))
    if job.globs:
        text += "\n" + yaml.dump({"globs": job.globs})
    atomic_write(schedule_yaml, text)
    ui.good(f"declared {schedule_yaml}")

    # `plane apply` plans from the snapshot; without this refresh the just-written
    # job file is invisible and the hinted next step reports "no changes planned".
    from planeops.core.observe import run_observe

    snap = run_observe(repo)
    observed_keys = {
        f"{o.get('adapter')}/{o.get('native_id')}" for o in snap["observed"]
    }
    job_ids = {e.get("id") for e in job.entries if isinstance(e, dict)}
    if job_ids & observed_keys:
        ui.good(
            f"observed {len(snap['observed'])} fact(s); the new job is in the snapshot"
        )
        ui.line(job.hint)
    else:
        # The scan can fail silently (e.g. no user session bus); claiming
        # presence then would be a lie. Say what actually happened.
        ui.warn(
            "warning: the new job did not appear in the snapshot (adapter scan "
            "failed? see `plane drift` alerts); fix that, then `plane observe` "
            "and `plane apply`",
            stderr=True,
        )
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "schedule",
        help="set up the ambient reconcile timer (then `plane apply` loads it)",
        description=(
            "Write the OS-native timer files (launchd on macOS, systemd on Linux) "
            "that run `plane reconcile` on an interval, plus a registry entry "
            "declaring the job, all previewed and confirmed first. The job itself "
            "is then governed like any other entry: `plane apply` loads it, "
            "--off retires it."
        ),
    )
    p.add_argument(
        "--every", default="6h", help="run interval: 6h / 30m / 90s (default 6h)"
    )
    p.add_argument(
        "--no-login", action="store_true", help="don't also run at login/boot"
    )
    p.add_argument(
        "--off", action="store_true", help="retire the schedule (apply then unloads it)"
    )
    p.add_argument(
        "--yes", action="store_true", help="skip the write confirmation prompt"
    )
    p.set_defaults(func=_cmd)
