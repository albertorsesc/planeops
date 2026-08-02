"""`plane init`: scaffold an instance and register it in ~/.config/planeops."""

from __future__ import annotations

import argparse
from pathlib import Path

from planeops.cli._text import n_entries


def _should_seed(args: argparse.Namespace) -> bool:
    """Seed the registry from the machine? --seed/--no-seed decide; otherwise offer it
    interactively (default yes), and skip when there is no readable stdin."""
    if args.no_seed:
        return False
    if args.seed:
        return True
    try:
        answer = input("seed the registry from this machine now? (Y/n) ")
    except (EOFError, OSError):
        return False  # non-interactive without --seed: leave the registry empty
    return answer.strip().lower()[:1] != "n"


def _seed_from_machine(inst: Path) -> None:
    """Observe the machine and land the proposal in the instance, so `plane init`
    ends with a governed registry to prune rather than a blank one to author."""
    import json

    from planeops.core.observe import run_observe
    from planeops.importers import discover_importers, write_proposal

    print("seeding the registry from this machine (observe -> import)...")
    snap = run_observe(inst)
    entries = discover_importers()["observed"].propose(json.dumps(snap), inst)
    if not entries:
        print("  nothing observed to seed")
        return
    written, total = write_proposal(entries, inst)
    print(f"  wrote {n_entries(len(entries))} to {written}; prune, then `plane drift`")


def _resolve_target(args: argparse.Namespace) -> Path | None:
    """Where the instance goes: an explicit path wins; otherwise ASK, the same
    show-and-confirm posture as every other write in the tool. Any valid path
    is a first-class answer (hidden directories, nested paths, anywhere).
    Enter accepts the suggested default; no stdin and no --yes means refuse to
    guess, never a silent placement."""
    if args.path:
        return Path(args.path)
    default = Path.home() / "planeops"
    if args.yes:
        return default
    try:
        answer = input(f"create the instance at {default}? (path or Enter to accept) ")
    except (EOFError, OSError):
        import sys

        print(
            "no path given and no way to ask: pass a path "
            "(`plane init <path>`) or --yes for the default",
            file=sys.stderr,
        )
        return None
    return Path(answer.strip()).expanduser() if answer.strip() else default


def _cmd(args: argparse.Namespace) -> int:
    from planeops.core.init import init_instance
    from planeops.core.locate import config_home

    path = _resolve_target(args)
    if path is None:
        return 1
    for action in init_instance(path, config_home(), force=args.force):
        print(action)
    inst = path.expanduser().resolve()
    print(f"\ninstance ready at {inst}")
    if _should_seed(args):
        _seed_from_machine(inst)
    else:
        print("next: `plane observe && plane import observed --write`, then drift")
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "init", help="scaffold an instance and register it in ~/.config/planeops"
    )
    p.add_argument(
        "path",
        nargs="?",
        default=None,
        help="instance dir, any valid path (omit to be asked; default ~/planeops)",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="accept the default location without asking",
    )
    p.add_argument(
        "--force", action="store_true", help="repoint config.toml if it points away"
    )
    p.add_argument(
        "--seed", action="store_true", help="also observe + seed the registry now"
    )
    p.add_argument(
        "--no-seed", action="store_true", help="scaffold only; don't offer to seed"
    )
    p.set_defaults(func=_cmd)
