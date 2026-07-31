"""pkg-npm adapter (global npm packages).

observe reports globally installed npm packages and versions from
`npm ls -g --depth=0 --json`. plan/execute converge presence: install an absent
active package, uninstall a present retired one.

OS access goes through the injected `run` seam, so the adapter is testable against
recorded `npm` output and never shells out under test.
"""

from __future__ import annotations

import json

from engine._run import Runner, default_run
from engine.core.contracts import Change, Ctx, Observed, Result
from engine.core.schema import ABSENT_LIFECYCLES, Entry


def parse_npm_globals(text: str) -> dict[str, str]:
    """Map package -> version from `npm ls -g --json`. Tolerant of the empty or
    non-JSON output npm emits when it is absent or unhappy."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    deps = data.get("dependencies", {})
    out: dict[str, str] = {}
    if isinstance(deps, dict):
        for name, meta in deps.items():
            version = meta.get("version") if isinstance(meta, dict) else None
            if isinstance(version, str):
                out[name] = version
    return out


class PkgNpmAdapter:
    name = "pkg-npm"
    domains: tuple[str, ...] = ("package",)
    # Converge order: packages land early so later phases find their tools.
    default_phase = 2
    # A confirmed global install may fetch on a cold cache for minutes; no
    # ceiling, the human owns the wait.
    EXECUTE_TIMEOUT: float | None = None

    def __init__(self, run: Runner | None = None):
        self._run = run or default_run

    def observe(self, ctx: Ctx) -> list[Observed]:
        # `npm ls -g` exits non-zero on dep-tree warnings while still printing
        # valid JSON, so parse the output regardless of the exit code.
        res = self._run(["npm", "ls", "-g", "--depth=0", "--json"])
        return [
            Observed(adapter=self.name, native_id=name, facts={}, version=version)
            for name, version in parse_npm_globals(res.out).items()
        ]

    def plan(self, entry: Entry, obs: Observed | None, ctx: Ctx) -> list[Change]:
        package = entry.native_id
        if entry.lifecycle in ABSENT_LIFECYCLES:
            if obs is None:
                return []  # already absent as desired
            return [
                Change(
                    entry_id=entry.id,
                    kind="remove",
                    diff=f"npm: uninstall -g {package} (version {obs.version})",
                    action={"op": "uninstall", "package": package},
                )
            ]
        if obs is None:
            return [
                Change(
                    entry_id=entry.id,
                    kind="install",
                    diff=f"npm: install -g {package}",
                    action={"op": "install", "package": package},
                )
            ]
        return []

    def execute(self, change: Change, ctx: Ctx) -> Result:
        action = change.action
        op = action.get("op")
        package = action.get("package", "")
        if op == "install":
            res = self._run(
                ["npm", "install", "-g", package], timeout=self.EXECUTE_TIMEOUT
            )
        elif op == "uninstall":
            res = self._run(
                ["npm", "uninstall", "-g", package], timeout=self.EXECUTE_TIMEOUT
            )
        else:
            return Result(ok=False, detail=f"unknown npm op {op!r}")
        if res.code != 0:
            detail = res.err.strip() or str(res.code)
            return Result(ok=False, detail=f"npm {op} {package} failed: {detail}")
        return Result(ok=True, detail=f"npm {op} {package}")


ADAPTER = PkgNpmAdapter()
