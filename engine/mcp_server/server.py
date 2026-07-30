"""The MCP server: exposes planeops's read verbs as tools over stdio.

Four tools, thin wrappers over engine.mcp_server.tools: `planeops_observe` rescans
the machine and records a snapshot (a writer, so annotated not-read-only,
not-idempotent); `planeops_drift`, `planeops_status`, and `planeops_mcp` are pure
reads (read-only + idempotent) that report drift, the last recorded drift without
rescanning, and the cross-client MCP view. None converges the managed machine. There
are deliberately NO mutation tools: apply stays behind the CLI's per-change
confirmation gate, so an assistant can read state but never converge it unattended.

Run with `plane-mcp` (needs the `mcp` extra) or `python -m engine.mcp_server.server`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from engine import __version__
from engine.core.locate import resolve_instance_root
from engine.mcp_server.tools import (
    drift_state,
    mcp_view_state,
    observe_state,
    status_state,
)

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


def _root(repo: str | None) -> Path:
    """Resolve the instance the same way the CLI does: an explicit `repo` wins, else
    $PLANEOPS_INSTANCE, the ~/.config/planeops pointer, then the cwd marker walk.
    An MCP client's cwd is arbitrary (often / or $HOME), so resolving from cwd alone
    answered from the wrong instance and wrote state outside it."""
    return resolve_instance_root(repo)


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
    def planeops_observe(repo: str | None = None) -> dict[str, Any]:
        return observe_state(_root(repo))

    @mcp.tool(
        annotations=_PURE_READ,
        description=(
            "Report drift between declared desired state and the last observed "
            "snapshot, as structured triage (alerts / report / uncovered / re-auth) "
            "with an exit_code (2 iff alerts). A pure read: writes nothing. Call "
            "planeops_observe first for a current answer."
        ),
    )
    def planeops_drift(repo: str | None = None) -> dict[str, Any]:
        return drift_state(_root(repo))

    @mcp.tool(
        annotations=_PURE_READ,
        description=(
            "The last drift report without rescanning (the cheap 'is there drift "
            "right now?' read): alert count and triage from the recorded DRIFT.json. "
            "A pure read; returns a structured error if nothing has been recorded yet."
        ),
    )
    def planeops_status(repo: str | None = None) -> dict[str, Any]:
        return status_state(_root(repo))

    @mcp.tool(
        annotations=_PURE_READ,
        description=(
            "Cross-client view of MCP servers from the last snapshot: every server "
            "and which clients it is wired into, flagging single-client (reuse "
            "candidates), the same tool under different names, and ungoverned servers "
            "(observed but not declared). A pure read; error if no snapshot yet."
        ),
    )
    def planeops_mcp(repo: str | None = None) -> dict[str, Any]:
        return mcp_view_state(_root(repo))

    return mcp


def main() -> None:
    build_server().run()  # stdio transport by default


if __name__ == "__main__":
    main()
