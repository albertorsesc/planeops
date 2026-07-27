"""`plane` CLI. Verbs: observe, drift, apply, import.

observe and drift are read-only. apply renders a diff and requires confirmation
before each mutation; the engine owns that gate, not the adapters.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

from engine import __version__


def find_repo_root(start: Path) -> Path:
    """Walk up from `start` to the directory holding SPEC.md or registry/."""
    for candidate in (start, *start.parents):
        if (candidate / "SPEC.md").is_file() or (candidate / "registry").is_dir():
            return candidate
    return start


def _cmd_observe(args: argparse.Namespace) -> int:
    from engine.core.observe import run_observe

    repo = find_repo_root(Path(args.repo).resolve())
    snap = run_observe(repo, attest=args.attest)
    print(
        f"observed {len(snap['observed'])} fact(s), "
        f"{len(snap['uncovered'])} uncovered adapter(s) "
        f"-> observed/{snap['host']}/snapshot.json"
    )
    return 0


def _cmd_drift(args: argparse.Namespace) -> int:
    from engine.core.drift import run_drift

    repo = find_repo_root(Path(args.repo).resolve())
    try:
        report = run_drift(repo)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        f"{report.alert_count} alert(s), {len(report.report)} report, "
        f"{len(report.uncovered)} uncovered -> observed/{report.host}/DRIFT.md"
    )
    return 2 if report.alert_count else 0


def _cmd_apply(args: argparse.Namespace) -> int:
    from engine.core.apply import run_apply

    repo = find_repo_root(Path(args.repo).resolve())
    try:
        applied = run_apply(repo, only_id=args.id, only_phase=args.phase)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not applied:
        print("no changes to apply; machine matches desired state")
        return 0

    executed = [a for a in applied if a.executed]
    skipped = [a for a in applied if not a.executed]
    failed = [a for a in executed if not (a.result and a.result.ok)]
    for a in executed:
        status = "ok" if (a.result and a.result.ok) else "FAILED"
        print(
            f"  [{status}] {a.change.entry_id}: {a.result.detail if a.result else ''}"
        )
    print(f"{len(executed)} applied ({len(failed)} failed), {len(skipped)} skipped")
    return 1 if failed else 0


def _cmd_import(args: argparse.Namespace) -> int:
    if args.kind != "stackfile":
        print(f"unknown import kind {args.kind!r}", file=sys.stderr)
        return 1
    from engine.importers.stackfile import load_rules, parse_stackfile, render_proposal

    path = Path(args.path)
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 1
    repo = find_repo_root(Path(args.repo).resolve())
    entries = parse_stackfile(path.read_text(), load_rules(repo))
    print(
        f"# proposed {len(entries)} entr(ies) from {path} "
        "- review, then save into registry/"
    )
    print(render_proposal(entries), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plane", description="personal AI control plane"
    )
    parser.add_argument("--version", action="version", version=f"plane {__version__}")
    parser.add_argument("--repo", default=".", help="instance repo root (default: cwd)")
    sub = parser.add_subparsers(dest="verb", required=True)

    p_observe = sub.add_parser(
        "observe", help="scan the machine, write a snapshot (read-only)"
    )
    p_observe.add_argument(
        "--attest", action="store_true", help="record fresh manual attestations"
    )
    p_observe.set_defaults(func=_cmd_observe)

    p_drift = sub.add_parser("drift", help="diff desired vs observed, write DRIFT.md")
    p_drift.set_defaults(func=_cmd_drift)

    p_apply = sub.add_parser("apply", help="converge confirmed changes, one at a time")
    p_apply.add_argument("--id", default=None, help="apply only the entry with this id")
    p_apply.add_argument(
        "--phase",
        type=int,
        default=None,
        help="apply only entries in this converge phase",
    )
    p_apply.set_defaults(func=_cmd_apply)

    p_import = sub.add_parser("import", help="propose registry entries from a manifest")
    p_import.add_argument("kind", choices=["stackfile"])
    p_import.add_argument("path")
    p_import.set_defaults(func=_cmd_import)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return cast(int, args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
