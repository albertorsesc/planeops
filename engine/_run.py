"""Shared subprocess seam.

A neutral top-level module (not under `adapters/`) so anything that shells out can
depend on it without creating a core -> adapters import edge. Every adapter that
shells out takes a `Runner` in its constructor and defaults to `default_run`, and
the sops secrets backend uses it too. Tests inject a canned runner so callers are
exercised against recorded tool output and never touch the real machine. The
engine's diff/triage logic does not shell out.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RunResult:
    code: int
    out: str = ""
    err: str = ""


class Runner(Protocol):
    """The call shape every runner (real or fake) satisfies. `timeout` is
    per-call because it belongs to the OPERATION, not the adapter: an observe
    probe (`brew list`) should fail fast, while a confirmed converge
    (`brew install`, `ollama pull`) may legitimately run for many minutes and
    passes a higher ceiling or None."""

    def __call__(self, cmd: list[str], *, timeout: float | None = 30) -> RunResult: ...


def default_run(cmd: list[str], *, timeout: float | None = 30) -> RunResult:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        # 124 per the GNU-timeout convention, and a distinct message: unlike a
        # missing binary, the killed child's own children may STILL be running
        # and mutating the machine, and the operator needs to know that.
        return RunResult(
            124,
            "",
            f"timed out after {timeout}s; the underlying command may still be running",
        )
    except OSError as exc:
        return RunResult(127, "", str(exc))
    return RunResult(proc.returncode, proc.stdout, proc.stderr)
