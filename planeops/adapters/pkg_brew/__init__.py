"""pkg-brew adapter (Homebrew formulae).

observe reports installed formulae and their versions from `brew list --versions
--formula`, so drift catches a formula listed active that is not installed, or a
retired one still present. plan/execute converge presence: install an absent
active formula, uninstall a present retired one. Casks (GUI apps) are out of
scope and can be a separate adapter.

OS access goes through the injected `run` seam, so the adapter is testable
against recorded `brew` output and never shells out under test.
"""

from __future__ import annotations

from planeops._run import Runner, default_run
from planeops.core.contracts import Change, Ctx, Observed, Result
from planeops.core.schema import ABSENT_LIFECYCLES, Entry


def parse_brew_versions(text: str) -> dict[str, str]:
    """Map formula -> installed version from `brew list --versions` output. Each
    line is `name version [version...]`; the last version wins when several are
    installed (the most recent)."""
    versions: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        versions[parts[0]] = parts[-1]
    return versions


class PkgBrewAdapter:
    name = "pkg-brew"
    domains: tuple[str, ...] = ("package",)
    # Converge order: packages land early so later phases (models, services)
    # find their tools installed.
    default_phase = 2
    # A confirmed install may download and compile for many minutes; no ceiling.
    # The human just confirmed the change and owns the wait (Ctrl-C aborts).
    EXECUTE_TIMEOUT: float | None = None

    def __init__(self, run: Runner | None = None):
        self._run = run or default_run

    def observe(self, ctx: Ctx) -> list[Observed]:
        res = self._run(["brew", "list", "--versions", "--formula"])
        if res.code != 0:
            return []  # brew absent or errored: report nothing rather than crash
        return [
            Observed.of(self.name, name, version=version)
            for name, version in parse_brew_versions(res.out).items()
        ]

    def plan(self, entry: Entry, obs: Observed | None, ctx: Ctx) -> list[Change]:
        formula = entry.native_id
        if entry.lifecycle in ABSENT_LIFECYCLES:
            if obs is None:
                return []  # already absent as desired
            return [
                Change(
                    entry_id=entry.id,
                    kind="remove",
                    diff=f"brew: uninstall {formula} (version {obs.version})",
                    action={"op": "uninstall", "formula": formula},
                )
            ]
        if obs is None:
            return [
                Change(
                    entry_id=entry.id,
                    kind="install",
                    diff=f"brew: install {formula}",
                    action={"op": "install", "formula": formula},
                )
            ]
        return []

    def execute(self, change: Change, ctx: Ctx) -> Result:
        action = change.action
        op = action.get("op")
        formula = action.get("formula", "")
        if op == "install":
            res = self._run(["brew", "install", formula], timeout=self.EXECUTE_TIMEOUT)
        elif op == "uninstall":
            res = self._run(
                ["brew", "uninstall", formula], timeout=self.EXECUTE_TIMEOUT
            )
        else:
            return Result(ok=False, detail=f"unknown brew op {op!r}")
        if res.code != 0:
            detail = res.err.strip() or str(res.code)
            return Result(ok=False, detail=f"brew {op} {formula} failed: {detail}")
        return Result(ok=True, detail=f"brew {op} {formula}")


ADAPTER = PkgBrewAdapter()
