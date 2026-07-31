"""pkg-uv adapter (uv-installed CLI tools).

observe reports the tools installed via `uv tool install`, from `uv tool list`.
plan/execute converge presence: install an absent active tool, uninstall a present
retired one. This covers uv-managed tools, not the uv binary itself.

OS access goes through the injected `run` seam, so the adapter is testable against
recorded `uv` output and never shells out under test.
"""

from __future__ import annotations

from engine._run import Runner, default_run
from engine.core.contracts import Change, Ctx, Observed, Result
from engine.core.schema import ABSENT_LIFECYCLES, Entry


def parse_uv_tools(text: str) -> dict[str, str]:
    """Map tool name -> version from `uv tool list`. Tool lines are `name vX.Y.Z`;
    the indented `- executable` lines under each tool are skipped."""
    tools: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line[0].isspace() or line.startswith("-"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith("v"):
            tools[parts[0]] = parts[1][1:]
    return tools


class PkgUvAdapter:
    name = "pkg-uv"
    domains: tuple[str, ...] = ("package",)
    # A confirmed tool install resolves and downloads; no ceiling, the human
    # owns the wait.
    EXECUTE_TIMEOUT: float | None = None

    def __init__(self, run: Runner | None = None):
        self._run = run or default_run

    def observe(self, ctx: Ctx) -> list[Observed]:
        res = self._run(["uv", "tool", "list"])
        if res.code != 0:
            return []  # uv absent or errored: report nothing rather than crash
        return [
            Observed(adapter=self.name, native_id=name, facts={}, version=version)
            for name, version in parse_uv_tools(res.out).items()
        ]

    def plan(
        self, entry: Entry, obs: Observed | None, ctx: Ctx | None = None
    ) -> list[Change]:
        tool = entry.native_id
        if entry.lifecycle in ABSENT_LIFECYCLES:
            if obs is None:
                return []  # already absent as desired
            return [
                Change(
                    entry_id=entry.id,
                    kind="remove",
                    diff=f"uv: uninstall tool {tool} (version {obs.version})",
                    action={"op": "uninstall", "tool": tool},
                )
            ]
        if obs is None:
            return [
                Change(
                    entry_id=entry.id,
                    kind="install",
                    diff=f"uv: install tool {tool}",
                    action={"op": "install", "tool": tool},
                )
            ]
        return []

    def execute(self, change: Change, ctx: Ctx) -> Result:
        action = change.action
        op = action.get("op")
        tool = action.get("tool", "")
        if op == "install":
            res = self._run(
                ["uv", "tool", "install", tool], timeout=self.EXECUTE_TIMEOUT
            )
        elif op == "uninstall":
            res = self._run(
                ["uv", "tool", "uninstall", tool], timeout=self.EXECUTE_TIMEOUT
            )
        else:
            return Result(ok=False, detail=f"unknown uv op {op!r}")
        if res.code != 0:
            detail = res.err.strip() or str(res.code)
            return Result(ok=False, detail=f"uv tool {op} {tool} failed: {detail}")
        return Result(ok=True, detail=f"uv tool {op} {tool}")


ADAPTER = PkgUvAdapter()
