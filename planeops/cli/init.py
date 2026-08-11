"""`plane init`: scaffold an instance and register it in ~/.config/planeops."""

from __future__ import annotations

import argparse
from pathlib import Path

from planeops.cli._text import n_entries
from planeops.core.prompt import ask


def _should_seed(args: argparse.Namespace) -> bool:
    """Seed the registry from the machine? --seed/--no-seed decide; otherwise offer it
    interactively (default yes), and skip when there is no readable stdin."""
    if args.no_seed:
        return False
    if args.seed:
        return True
    answer = ask("seed the registry from this machine now? (Y/n) ")
    if answer is None:
        return False  # nobody to ask, and no --seed: leave the registry empty
    return answer.strip().lower()[:1] != "n"


def _seed_from_machine(inst: Path) -> None:
    """Observe the machine and land the proposal in the instance, so `plane init`
    ends with a governed registry to prune rather than a blank one to author."""
    import json

    from planeops.core.observe import run_observe
    from planeops.importers import discover_importers, write_proposal
    from planeops.providers import ui

    ui.line("seeding the registry from this machine (observe -> import)...")
    snap = run_observe(inst)
    entries = discover_importers()["observed"].propose(json.dumps(snap), inst)
    if not entries:
        ui.line("  nothing observed to seed")
        return
    written, total = write_proposal(entries, inst)
    ui.good(
        f"  wrote {n_entries(len(entries))} to {written}; prune, then `plane drift`"
    )


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
    answer = ask(f"create the instance at {default}? (path or Enter to accept) ")
    if answer is None:
        from planeops.providers import ui

        ui.err(
            "no path given and no way to ask: pass a path "
            "(`plane init <path>`) or --yes for the default"
        )
        return None
    return Path(answer.strip()).expanduser() if answer.strip() else default


def _print_sections(args: argparse.Namespace) -> int:
    """Hand over the blocks an existing instance has not adopted, on stdout so
    `>> instance.yaml` works. Nothing is written here: the file is the
    operator's, and a config that edits itself is one they no longer know."""
    from planeops.cli.instance import instance_root
    from planeops.core.sections import missing_sections
    from planeops.providers import ui

    repo = Path(args.path).expanduser() if args.path else instance_root(args)
    instance_yaml = repo / "instance.yaml"
    text = instance_yaml.read_text() if instance_yaml.is_file() else ""
    missing = missing_sections(text)
    if not missing:
        ui.good(f"{instance_yaml} already configures every documented section")
        return 0
    ui.note(
        f"# {len(missing)} section(s) this build documents that "
        f"{instance_yaml} does not set."
    )
    ui.note(f"# Append with: plane init --sections >> {instance_yaml}")
    for _, block in missing:
        print()
        print(block, end="")
    return 0


def _cmd(args: argparse.Namespace) -> int:
    from planeops.core.init import init_instance
    from planeops.core.locate import config_home
    from planeops.providers import ui

    if args.sections:
        return _print_sections(args)

    path = _resolve_target(args)
    if path is None:
        return 1
    for action in init_instance(path, config_home(), force=args.force):
        ui.line(action)
    inst = path.expanduser().resolve()
    ui.line("")
    ui.good(f"instance ready at {inst}")
    if _should_seed(args):
        _seed_from_machine(inst)
    else:
        ui.line("next: `plane observe && plane import observed --write`, then drift")
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "init",
        help="scaffold an instance and register it in ~/.config/planeops",
        description=(
            "Create a planeops instance: the directory that holds your registry "
            "(desired state), instance.yaml (this machine's adapter settings), and "
            "generated observations. Asks where to put it unless a path or --yes "
            "is given, then offers to seed the registry from what is already "
            "installed so onboarding is pruning, not authoring."
        ),
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
    p.add_argument(
        "--sections",
        action="store_true",
        help="print the documented instance.yaml sections this instance has not "
        "adopted, for pasting (append with >>); writes nothing",
    )
    p.set_defaults(func=_cmd)
