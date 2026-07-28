"""Shared subprocess seam for adapters.

Every adapter that shells out takes a `Runner` in its constructor and defaults to
`default_run`. Tests inject a canned runner so an adapter is exercised against
recorded tool output and never touches the real machine. The sops secrets backend
uses it too; the engine's diff/triage logic does not shell out.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunResult:
    code: int
    out: str = ""
    err: str = ""


Runner = Callable[[list[str]], RunResult]


def default_run(cmd: list[str]) -> RunResult:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return RunResult(127, "", str(exc))
    return RunResult(proc.returncode, proc.stdout, proc.stderr)
