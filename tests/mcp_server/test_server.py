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


def test_exposes_exactly_the_two_read_verbs():
    # Locks the surface: a future mutation tool (e.g. tarmac_apply) would fail here.
    assert set(_tools_by_name(build_server())) == {"tarmac_observe", "tarmac_drift"}


def test_no_tool_is_destructive_and_drift_is_a_pure_read():
    # The invariant: an assistant can read state but never converge it. No tool is
    # destructive; drift is a pure read (read-only + idempotent); observe is the one
    # writer (it records a snapshot), so it is honestly not-read-only.
    tools = _tools_by_name(build_server())
    for name, tool in tools.items():
        assert tool.annotations is not None, name
        assert tool.annotations.destructive_hint in (None, False), name
    assert tools["tarmac_drift"].annotations.read_only_hint is True
    assert tools["tarmac_drift"].annotations.idempotent_hint is True
    assert tools["tarmac_observe"].annotations.read_only_hint is False


def test_drift_tool_call_returns_structured_content(tmp_path):
    # A real call over the MCP boundary. A repo with no snapshot gives the structured
    # "observe first" error: proves the tool is wired, returns structured_content,
    # and never raises across the boundary.
    res = asyncio.run(build_server().call_tool("tarmac_drift", {"repo": str(tmp_path)}))
    assert res.is_error is False
    assert "error" in res.structured_content
