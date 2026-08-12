"""ollama adapter (local models).

observe reports the models `ollama list` shows, recording each model's content
digest as its version, so drift catches a model listed active that is not pulled,
or a retired one still on disk. plan/execute converge presence: pull an absent
active model, remove a present retired one.

OS access goes through the injected `run` seam, so the adapter is testable
against recorded `ollama` output and never shells out under test.
"""

from __future__ import annotations

from planeops._run import Runner, default_run
from planeops.core.contracts import Change, Ctx, Observed, Result
from planeops.core.schema import ABSENT_LIFECYCLES, Entry


def parse_ollama_list(text: str) -> dict[str, dict[str, str]]:
    """Map model name -> {id, size} from `ollama list` output. Columns are
    whitespace-aligned; NAME and ID are the reliable first two tokens and SIZE is
    the next two ("18 GB"). The header row and short lines are skipped."""
    models: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0] == "NAME":
            continue
        name, model_id, size = parts[0], parts[1], f"{parts[2]} {parts[3]}"
        models[name] = {"id": model_id, "size": size}
    return models


class OllamaAdapter:
    name = "ollama"
    domains: tuple[str, ...] = ("model",)
    # Converge order: models after packages/config (the runtime must exist),
    # before services that may depend on them.
    default_phase = 4
    # Pulling a large model is tens of gigabytes; no ceiling on a confirmed
    # pull/remove, the human owns the wait.
    EXECUTE_TIMEOUT: float | None = None

    def __init__(self, run: Runner | None = None):
        self._run = run or default_run

    def observe(self, ctx: Ctx) -> list[Observed]:
        res = self._run(["ollama", "list"])
        if res.code != 0:
            return []  # ollama absent or errored: report nothing rather than crash
        return [
            Observed.of(
                self.name, name, version=meta["id"], detail={"size": meta["size"]}
            )
            for name, meta in parse_ollama_list(res.out).items()
        ]

    def plan(self, entry: Entry, obs: Observed | None, ctx: Ctx) -> list[Change]:
        model = entry.native_id
        if entry.lifecycle in ABSENT_LIFECYCLES:
            if obs is None:
                return []  # already absent as desired
            return [
                Change(
                    entry_id=entry.id,
                    kind="remove",
                    diff=f"ollama: remove {model} ({obs.facts.get('size', '?')})",
                    action={"op": "remove", "model": model},
                )
            ]
        if obs is None:
            return [
                Change(
                    entry_id=entry.id,
                    kind="install",
                    diff=f"ollama: pull {model}",
                    action={"op": "pull", "model": model},
                )
            ]
        return []

    def execute(self, change: Change, ctx: Ctx) -> Result:
        action = change.action
        op = action.get("op")
        model = action.get("model", "")
        if op == "pull":
            res = self._run(["ollama", "pull", model], timeout=self.EXECUTE_TIMEOUT)
        elif op == "remove":
            res = self._run(["ollama", "rm", model], timeout=self.EXECUTE_TIMEOUT)
        else:
            return Result(ok=False, detail=f"unknown ollama op {op!r}")
        if res.code != 0:
            detail = res.err.strip() or str(res.code)
            return Result(ok=False, detail=f"ollama {op} {model} failed: {detail}")
        return Result(ok=True, detail=f"ollama {op} {model}")


ADAPTER = OllamaAdapter()
