"""`plane` CLI. Verbs: init, observe, drift, reconcile, apply, import, status, mcp.

observe, drift, status, and mcp are read-only; reconcile is observe+drift in one pass
(for a scheduler); init scaffolds an instance + the home config pointer. apply renders
a diff and requires confirmation before each mutation; the engine owns that gate, not
the adapters.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from engine import __version__
from engine.core.locate import resolve_instance_root


def _cmd_observe(args: argparse.Namespace) -> int:
    from engine.core.observe import run_observe

    repo = resolve_instance_root(args.repo)
    snap = run_observe(repo, attest=args.attest)
    print(
        f"observed {len(snap['observed'])} fact(s), "
        f"{len(snap['uncovered'])} uncovered adapter(s) "
        f"-> observed/{snap['host']}/snapshot.json"
    )
    return 0


def _cmd_drift(args: argparse.Namespace) -> int:
    from engine.core.drift import run_drift

    repo = resolve_instance_root(args.repo)
    try:
        report = run_drift(repo)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.as_json:
        from engine.core.report import render_drift_json

        print(render_drift_json(report), end="")  # stdout is pure JSON, pipeable
    else:
        print(
            f"{report.alert_count} alert(s), {len(report.report)} report, "
            f"{len(report.uncovered)} uncovered -> observed/{report.host}/DRIFT.md"
        )
    return 2 if report.alert_count else 0


def _cmd_apply(args: argparse.Namespace) -> int:
    from engine.core.apply import run_apply

    repo = resolve_instance_root(args.repo)
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
    if executed:
        from engine.core.observe import run_observe

        run_observe(repo)  # re-observe so `plane drift` reflects this apply (SPEC §5)
    return 1 if failed else 0


def _cmd_status(args: argparse.Namespace) -> int:
    from engine.core.status import read_status

    repo = resolve_instance_root(args.repo)
    data = read_status(repo)  # last DRIFT.json, no recompute
    if data is None:
        if not args.short:  # a prompt wants silence, not an error, when unseeded
            print("no drift report yet; run `plane drift`", file=sys.stderr)
        return 0
    if args.as_json:
        print(json.dumps(data, indent=2))
    elif args.short:  # a shell-prompt token: nothing when clean
        if data["alert_count"]:
            print(f"drift:{data['alert_count']}")
    else:
        summary = data["summary"]
        print(
            f"{data['alert_count']} alert(s), {summary['report']} report, "
            f"{summary['uncovered']} uncovered (as of {data['ts']})"
        )
    return 2 if data["alert_count"] else 0


def _cmd_reconcile(args: argparse.Namespace) -> int:
    from engine.core.drift import run_drift
    from engine.core.observe import run_observe
    from engine.core.schema import SchemaError

    repo = resolve_instance_root(args.repo)
    try:
        snap = run_observe(repo)  # scan + write the snapshot
    except SchemaError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        f"observed {len(snap['observed'])} fact(s) "
        f"-> observed/{snap['host']}/snapshot.json"
    )
    try:
        report = run_drift(repo)  # diff the fresh snapshot, write DRIFT.md + DRIFT.json
    except (FileNotFoundError, SchemaError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        f"{report.alert_count} alert(s), {len(report.report)} report, "
        f"{len(report.uncovered)} uncovered -> observed/{report.host}/DRIFT.md"
    )
    return 2 if report.alert_count else 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    from engine.core.mcp_view import read_mcp_view, render_mcp_view

    repo = resolve_instance_root(args.repo)
    view = read_mcp_view(repo)  # last snapshot + registry, no recompute
    if view is None:
        print("no snapshot yet; run `plane observe`", file=sys.stderr)
        return 0
    if args.as_json:
        print(json.dumps(view, indent=2))
    else:
        print(render_mcp_view(view), end="")
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    from engine.core.init import init_instance
    from engine.core.locate import config_home

    path = Path(args.path) if args.path else Path.cwd()
    for action in init_instance(path, config_home(), force=args.force):
        print(action)
    print(f"\ninstance ready at {path.expanduser().resolve()}")
    print("next: add entries to registry/ (or `plane import observed`), then observe")
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    from engine.importers import discover_importers, render_proposal, write_proposal

    path = Path(args.path)
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 1

    importer = discover_importers().get(args.kind)
    if importer is None:  # argparse choices normally prevents this
        print(f"unknown import kind {args.kind!r}", file=sys.stderr)
        return 1

    repo = resolve_instance_root(args.repo)
    entries = importer.propose(path.read_text(), repo)
    if args.adapter:  # onboard one type at a time (e.g. --adapter mcp)
        entries = [e for e in entries if e.get("adapter") == args.adapter]
        if not entries:  # clarify 0 results vs an unrecognized adapter name
            print(
                f"note: --adapter {args.adapter!r} matched no proposed entries",
                file=sys.stderr,
            )
    print(importer.note(path, len(entries)))

    if not args.write:  # default: propose to stdout, write nothing
        print(render_proposal(entries), end="")
        return 0

    # --write: land the proposal into registry/imported.yaml (a prune-not-author seed).
    if not entries:
        print("nothing new to import; the registry already covers the observed items")
        return 0
    target = repo / "registry" / "imported.yaml"
    if not args.yes:  # show the proposal and confirm before mutating the registry
        print(render_proposal(entries), end="")
        try:
            answer = input(f"write {len(entries)} entries to {target}? (y/N) ")
        except (EOFError, OSError):
            answer = ""  # no readable stdin: never write without an explicit --yes
        if answer.strip().lower()[:1] != "y":
            print("not written (use --yes to write non-interactively)", file=sys.stderr)
            return 0
    written, total = write_proposal(entries, repo)
    print(f"wrote {len(entries)} new entries to {written} ({total} total)")
    print("prune registry/imported.yaml to taste, then `plane drift`")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plane", description="personal AI control plane"
    )
    parser.add_argument("--version", action="version", version=f"plane {__version__}")
    parser.add_argument(
        "--repo",
        default=None,
        help="instance root; else $PLANEOPS_INSTANCE, ~/.config/planeops, or cwd",
    )
    sub = parser.add_subparsers(dest="verb", required=True)

    p_observe = sub.add_parser(
        "observe", help="scan the machine, write a snapshot (read-only)"
    )
    p_observe.add_argument(
        "--attest", action="store_true", help="record fresh manual attestations"
    )
    p_observe.set_defaults(func=_cmd_observe)

    p_drift = sub.add_parser(
        "drift", help="diff desired vs observed, write DRIFT.md + DRIFT.json"
    )
    p_drift.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="print the drift report as JSON to stdout (for piping / MCP)",
    )
    p_drift.set_defaults(func=_cmd_drift)

    p_status = sub.add_parser(
        "status", help="show the last drift report without recomputing (read-only)"
    )
    p_status.add_argument(
        "--json", dest="as_json", action="store_true",
        help="emit the stored drift report as JSON",
    )  # fmt: skip
    p_status.add_argument(
        "--short", action="store_true",
        help="compact indicator for a shell prompt (prints nothing when clean)",
    )  # fmt: skip
    p_status.set_defaults(func=_cmd_status)

    p_reconcile = sub.add_parser(
        "reconcile", help="observe then drift in one pass (for a scheduler)"
    )
    p_reconcile.set_defaults(func=_cmd_reconcile)

    p_mcp = sub.add_parser(
        "mcp",
        help="cross-client view of MCP servers from the last snapshot (read-only)",
    )
    p_mcp.add_argument(
        "--json", dest="as_json", action="store_true",
        help="emit the MCP view as JSON",
    )  # fmt: skip
    p_mcp.set_defaults(func=_cmd_mcp)

    p_init = sub.add_parser(
        "init", help="scaffold an instance and register it in ~/.config/planeops"
    )
    p_init.add_argument(
        "path", nargs="?", default=None, help="instance dir (default: cwd)"
    )
    p_init.add_argument(
        "--force", action="store_true", help="repoint config.toml if it points away"
    )
    p_init.set_defaults(func=_cmd_init)

    p_apply = sub.add_parser("apply", help="converge confirmed changes, one at a time")
    p_apply.add_argument("--id", default=None, help="apply only the entry with this id")
    p_apply.add_argument(
        "--phase",
        type=int,
        default=None,
        help="apply only entries in this converge phase",
    )
    p_apply.set_defaults(func=_cmd_apply)

    from engine.importers import discover_importers

    p_import = sub.add_parser("import", help="propose registry entries from a manifest")
    p_import.add_argument("kind", choices=sorted(discover_importers()))
    p_import.add_argument("path")
    p_import.add_argument(
        "--adapter",
        default=None,
        help="propose only entries for this adapter (onboard one type at a time)",
    )
    p_import.add_argument(
        "--write",
        action="store_true",
        help="land the proposal into registry/imported.yaml (de-duped) to prune",
    )
    p_import.add_argument(
        "--yes", action="store_true", help="with --write, skip the confirmation prompt"
    )
    p_import.set_defaults(func=_cmd_import)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return cast(int, args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
