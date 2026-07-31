"""chezmoi adapter (config/dotfile reproduction, delegated).

planeops does not reproduce config files itself: that is a solved, security-heavy
problem (path hardening, atomic writes, secrets, templating, permissions) that
chezmoi already owns. This adapter observes what chezmoi manages and whether each
file has drifted from its source, and converges by invoking `chezmoi apply` on the
drifted target. chezmoi does the writing; planeops governs it (drift + per-change
confirmation) as one domain among many.

observe reads `chezmoi managed` (the full set) and `chezmoi status` (the drifted
subset); a managed file carries `facts.drifted`. plan proposes `chezmoi apply
<path>` for a drifted, present-desired entry; execute runs it. Prerequisite: the
owner keeps their config in a chezmoi source repo; without chezmoi installed the
adapter observes nothing.

OS access goes through the injected `run` seam, so the adapter is testable against
recorded chezmoi output and never shells out under test.
"""

from __future__ import annotations

from engine._run import Runner, default_run
from engine.core.contracts import Change, Ctx, Observed, Result
from engine.core.schema import ABSENT_LIFECYCLES, Entry


def _abs_target(path: str, ctx: Ctx) -> str:
    """`chezmoi managed` yields home-relative paths; resolve to the absolute target
    `chezmoi apply` expects. An already-absolute path is returned unchanged."""
    if path.startswith("/") or ctx.platform is None:
        return path
    return str(ctx.platform.home() / path)


def parse_chezmoi_managed(text: str) -> list[str]:
    """The target paths chezmoi manages, one per line."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_chezmoi_status(text: str) -> set[str]:
    """Target paths that `chezmoi apply` would change. `chezmoi status` mimics
    `git status`: a two-char code then the path; the second char is the actual-vs-
    target difference, so a non-space there means the file has drifted from source."""
    drifted: set[str] = set()
    for line in text.splitlines():
        if len(line) < 3:
            continue
        code, path = line[:2], line[2:].strip()
        if code[1] != " " and path:
            drifted.add(path)
    return drifted


class ChezmoiAdapter:
    name = "chezmoi"
    domains: tuple[str, ...] = ("config",)
    # Applying one file is quick; bounded so a wedged chezmoi (e.g. an external
    # diff/merge tool it spawns) can't hang the whole apply run.
    EXECUTE_TIMEOUT: float | None = 300

    def __init__(self, run: Runner | None = None):
        self._run = run or default_run

    def observe(self, ctx: Ctx) -> list[Observed]:
        managed = self._run(["chezmoi", "managed"])
        if managed.code != 0:
            return []  # chezmoi absent or errored: report nothing rather than crash
        drifted = parse_chezmoi_status(self._run(["chezmoi", "status"]).out)
        return [
            Observed(
                adapter=self.name,
                native_id=path,
                facts={"drifted": path in drifted},
                version=None,
            )
            for path in parse_chezmoi_managed(managed.out)
        ]

    def plan(
        self, entry: Entry, obs: Observed | None, ctx: Ctx | None = None
    ) -> list[Change]:
        if entry.lifecycle in ABSENT_LIFECYCLES:
            return []  # removing a chezmoi-managed file is out of scope for v1
        if obs is None or not obs.facts.get("drifted"):
            return []  # not managed yet, or already matches source
        path = entry.native_id
        return [
            Change(
                entry_id=entry.id,
                kind="configure",
                diff=f"chezmoi: apply {path} (drifted from source)",
                action={"op": "apply", "path": path},
            )
        ]

    def execute(self, change: Change, ctx: Ctx) -> Result:
        action = change.action
        op = action.get("op")
        path = str(action.get("path", ""))
        if op != "apply":
            return Result(ok=False, detail=f"unknown chezmoi op {op!r}")
        # `chezmoi managed` yields home-relative paths, but `chezmoi apply` resolves
        # its argument against the CWD, so pass the absolute target. `--force`
        # because planeops already confirmed this change; without it chezmoi re-prompts
        # on a TTY when the target changed since it last wrote, which fails headless.
        target = _abs_target(path, ctx)
        res = self._run(
            ["chezmoi", "apply", "--force", target], timeout=self.EXECUTE_TIMEOUT
        )
        if res.code != 0:
            detail = res.err.strip() or str(res.code)
            return Result(ok=False, detail=f"chezmoi apply {target} failed: {detail}")
        return Result(ok=True, detail=f"chezmoi apply {target}")


ADAPTER = ChezmoiAdapter()
