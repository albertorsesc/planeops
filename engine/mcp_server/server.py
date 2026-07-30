"""The MCP server: exposes planeops's read verbs as tools over stdio.

Two tools, thin wrappers over engine.mcp_server.tools (which call run_observe /
run_drift): `planeops_observe` rescans the machine and records a snapshot (a writer,
so annotated not-read-only, not-idempotent), and `planeops_drift` reads the last
snapshot and reports drift (a pure read: writes nothing, read-only + idempotent).
Neither converges the managed machine. There are deliberately NO mutation tools:
apply stays behind the CLI's per-change confirmation gate, so an assistant can read
state but never converge it unattended.

Run with `plane-mcp` (needs the `mcp` extra) or `python -m engine.mcp_server.server`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from engine import __version__
from engine.core.locate import find_repo_root
from engine.mcp_server.tools import drift_state, observe_state

# drift is a pure read (writes nothing); observe re-scans the machine and records a
# fresh snapshot, so it is honestly a writer, not idempotent. Neither converges the
# managed machine: that is what "read-only server" means here.
_PURE_READ = ToolAnnotations(read_only_hint=True, idempotent_hint=True)
_REFRESH = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False
)

_INSTRUCTIONS = (
    "Read-only view of a machine's planeops control plane: no tool here converges or "
    "changes the managed machine. Call planeops_observe to refresh the recorded "
    "inventory (this rescans and writes a snapshot), then planeops_drift to see what "
    "has drifted from the declared desired state (a pure read of the last snapshot). "
    "Converging drift is the human's job via `plane apply`, behind a per-change "
    "confirmation gate."
)


def build_server() -> MCPServer:
    mcp = MCPServer("planeops", version=__version__, instructions=_INSTRUCTIONS)

    @mcp.tool(
        annotations=_REFRESH,
        description=(
            "Rescan this machine and record a fresh snapshot, returning an inventory "
            "summary: counts of what each adapter observed, plus declared-but-"
            "uncovered adapters. Writes snapshot.json (does not change the machine)."
        ),
    )
    def planeops_observe(repo: str = ".") -> dict[str, Any]:
        return observe_state(find_repo_root(Path(repo).resolve()))

    @mcp.tool(
        annotations=_PURE_READ,
        description=(
            "Report drift between declared desired state and the last observed "
            "snapshot, as structured triage (alerts / report / uncovered / re-auth) "
            "with an exit_code (2 iff alerts). A pure read: writes nothing. Call "
            "planeops_observe first for a current answer."
        ),
    )
    def planeops_drift(repo: str = ".") -> dict[str, Any]:
        return drift_state(find_repo_root(Path(repo).resolve()))

    return mcp


def main() -> None:
    build_server().run()  # stdio transport by default


if __name__ == "__main__":
    main()
