"""`plane secrets`: store lifecycle actions. `init` bootstraps the configured
store through its own provider, cwd-proof, with the standard confirm posture;
`add` writes one value through the store, prompted or piped, never on argv."""

from __future__ import annotations

import argparse
import getpass
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


def _cmd_add(args: argparse.Namespace) -> int:
    from planeops.core.schema import valid_secret_name
    from planeops.secrets import AcceptsValues
    from planeops.secrets.resolve import resolve_store

    repo = instance_root(args)
    store = resolve_store(repo)
    if store is None:
        raise LookupError("no secrets store is configured or shipped as default")
    if not isinstance(store, AcceptsValues):
        raise LookupError(
            f"the {store.name!r} store does not take values through "
            "`plane secrets add`; see its documentation for manual entry"
        )
    name = args.name
    if not valid_secret_name(name):
        raise LookupError(f"secret name {name!r} must match [A-Za-z0-9_.-]+")
    for line in store.add_preview(name):
        print(line)
    if sys.stdin.isatty():
        # The value is typed blind, so a typo would be invisible forever:
        # require the same blind entry twice before anything is written.
        value = getpass.getpass(f"value for {name!r} (input hidden): ")
        if value != getpass.getpass("repeat to confirm: "):
            raise LookupError("the two entries did not match; nothing written")
    else:
        if not args.yes:
            raise LookupError(
                "stdin is not a terminal; pass --yes to confirm a piped value"
            )
        value = sys.stdin.readline().rstrip("\n")
    if not value:
        raise LookupError("empty value; nothing written")
    print(store.add_value(name, value, force=args.force))
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("secrets", help="secrets store actions (init, add)")
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
    add = actions.add_parser(
        "add", help="add or rotate one secret's value (prompted or piped, never argv)"
    )
    add.add_argument("name", help="secret name, as written in secret://<name>")
    add.add_argument(
        "--force", action="store_true", help="rotate: overwrite an existing value"
    )
    add.add_argument(
        "--yes",
        action="store_true",
        help="required when the value arrives piped on stdin",
    )
    add.set_defaults(func=_cmd_add)
