"""`plane secrets`: store lifecycle actions. `init` bootstraps the configured
store through its own provider, cwd-proof, with the standard confirm posture."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from planeops.cli.instance import instance_root


def _cmd_init(args: argparse.Namespace) -> int:
    from planeops.secrets import BootstrapsStore
    from planeops.secrets.resolve import resolve_provider

    repo = instance_root(args)
    provider = resolve_provider(repo)
    if provider is None:
        raise LookupError("no secrets store is configured or shipped as default")
    if not isinstance(provider, BootstrapsStore):
        raise LookupError(
            f"the {provider.name!r} store does not self-bootstrap; "
            "see its documentation for manual setup"
        )
    age_key = Path(args.age_key).expanduser() if args.age_key else None
    print("secrets init will write:")
    for line in provider.bootstrap_preview(repo, age_key_file=age_key):
        print(f"  {line}")
    if not args.yes:
        try:
            answer = input("proceed? (y/N) ")
        except (EOFError, OSError):
            answer = ""
        if answer.strip().lower()[:1] != "y":
            print(
                "not initialized (use --yes to run non-interactively)",
                file=sys.stderr,
            )
            return 0
    for action in provider.bootstrap(repo, age_key_file=age_key):
        print(action)
    print("store ready; declare secrets in the registry, then `plane observe`")
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("secrets", help="secrets store actions (init)")
    actions = p.add_subparsers(dest="action", required=True)
    init = actions.add_parser(
        "init", help="bootstrap the configured store (identity, rules, empty store)"
    )
    init.add_argument(
        "--age-key",
        default=None,
        help="age identity file (default: where sops itself looks on this OS)",
    )
    init.add_argument(
        "--yes", action="store_true", help="write without the interactive confirm"
    )
    init.set_defaults(func=_cmd_init)
