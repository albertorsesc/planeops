"""The MCP server wiring, exercised through the real MCPServer interface (list_tools
/ call_tool). Skipped if the optional `mcp` dependency is absent, so the base gate
stays green without it.
"""

import asyncio

import pytest

pytest.importorskip("mcp")  # server module imports the optional dependency

from engine.mcp_server.server import build_server  # noqa: E402


def _tools_by_name(server):
    return {t.name: t for t in asyncio.run(server.list_tools())}


def test_exposes_the_read_verbs_only():
    # Locks the surface: reads only, a future mutation tool (planeops_apply) fails here.
    assert set(_tools_by_name(build_server())) == {
        "planeops_observe",
        "planeops_drift",
        "planeops_status",
        "planeops_mcp",
    }


def test_no_tool_is_destructive_and_the_reads_are_pure():
    # The invariant: an assistant can read state but never converge it. No tool is
    # destructive; drift/status/mcp are pure reads (read-only + idempotent); observe
    # is the one writer (it records a snapshot), so it is honestly not-read-only.
    tools = _tools_by_name(build_server())
    for name, tool in tools.items():
        assert tool.annotations is not None, name
        assert tool.annotations.destructive_hint in (None, False), name
    for pure in ("planeops_drift", "planeops_status", "planeops_mcp"):
        assert tools[pure].annotations.read_only_hint is True, pure
        assert tools[pure].annotations.idempotent_hint is True, pure
    assert tools["planeops_observe"].annotations.read_only_hint is False


def test_drift_tool_call_returns_structured_content(tmp_path):
    # A real call over the MCP boundary. A repo with no snapshot gives the structured
    # "observe first" error: proves the tool is wired, returns structured_content,
    # and never raises across the boundary.
    res = asyncio.run(
        build_server().call_tool("planeops_drift", {"repo": str(tmp_path)})
    )
    assert res.is_error is False
    assert "error" in res.structured_content
