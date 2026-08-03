"""`plane schedule`: set up the ambient reconcile timer (then `plane apply`
loads it). The per-OS backend is discovered; this module owns the CLI wiring,
the confirm gate, and the interval grammar."""

from __future__ import annotations

import argparse
import sys


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
    from planeops.core.statefile import atomic_write
    from planeops.importers import render_proposal
    from planeops.platform import current_platform
    from planeops.providers import yaml
    from planeops.schedulers import current_scheduler

    try:
        interval = _parse_every(args.every)
    except ValueError:
        print(f"--every must be like 6h/30m/90s (got {args.every!r})", file=sys.stderr)
        return 1

    home = current_platform().home()
    which = shutil.which("plane")
    plane = which or str(home / ".local" / "bin" / "plane")
    if which is None and not (home / ".local" / "bin" / "plane").exists():
        # The job would silently fail at fire time; say so at schedule time.
        print(
            f"warning: plane is not on PATH and {plane} does not exist; the "
            "scheduled job may fail until planeops is installed there",
            file=sys.stderr,
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
        print(str(exc), file=sys.stderr)  # ValueError is too broad to catch there)
        return 1

    repo = instance_root(args)
    # schedule writes machine state (job files + a registry entry): show what it
    # will write and confirm, the same posture as `import --write`. No readable
    # stdin and no --yes: write nothing.
    print("schedule will write:")
    for path in job.files:
        print(f"  {path}")
    print(f"  {repo / 'registry' / 'schedule.yaml'} declaring:")
    entry_doc: dict[str, object] = {"entries": job.entries}
    print("    " + yaml.dump(entry_doc).rstrip().replace("\n", "\n    "))
    if not args.yes:
        try:
            answer = input("proceed? (y/N) ")
        except (EOFError, OSError):
            answer = ""
        if answer.strip().lower()[:1] != "y":
            print("not written (use --yes to write non-interactively)", file=sys.stderr)
            return 0

    for path, content in job.files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, content)
        print(f"wrote {path}")

    schedule_yaml = repo / "registry" / "schedule.yaml"
    schedule_yaml.parent.mkdir(parents=True, exist_ok=True)
    text = render_proposal(list(job.entries))
    if job.globs:
        text += "\n" + yaml.dump({"globs": job.globs})
    atomic_write(schedule_yaml, text)
    print(f"declared {schedule_yaml}")

    # `plane apply` plans from the snapshot; without this refresh the just-written
    # job file is invisible and the hinted next step reports "no changes planned".
    from planeops.core.observe import run_observe

    snap = run_observe(repo)
    observed_keys = {
        f"{o.get('adapter')}/{o.get('native_id')}" for o in snap["observed"]
    }
    job_ids = {e.get("id") for e in job.entries if isinstance(e, dict)}
    if job_ids & observed_keys:
        print(
            f"observed {len(snap['observed'])} fact(s); the new job is in the snapshot"
        )
        print(job.hint)
    else:
        # Claiming presence here used to be a lie whenever the scan silently
        # failed (e.g. no user session bus). Say what actually happened.
        print(
            "warning: the new job did not appear in the snapshot (adapter scan "
            "failed? see `plane drift` alerts); fix that, then `plane observe` "
            "and `plane apply`",
            file=sys.stderr,
        )
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "schedule",
        help="set up the ambient reconcile timer (then `plane apply` loads it)",
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
