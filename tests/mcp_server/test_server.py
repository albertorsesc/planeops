"""The MCP server wiring, exercised through the real MCPServer interface (list_tools
/ call_tool). Skipped if the optional `mcp` dependency is absent, so the base gate
stays green without it.
"""

import asyncio

import pytest

pytest.importorskip("mcp")  # server module imports the optional dependency

from planeops.mcp_server.server import build_server  # noqa: E402


def _tools_by_name(server):
    return {t.name: t for t in asyncio.run(server.list_tools())}


def test_exposes_the_read_verbs_only():
    # Locks the surface: reads only, a future mutation tool (planeops_apply) fails here.
    assert set(_tools_by_name(build_server())) == {
        "planeops_observe",
        "planeops_drift",
        "planeops_status",
        "planeops_mcp",
        "planeops_secrets_list",
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
    # A real call over the MCP boundary. An instance with no snapshot gives the
    # structured "observe first" error: proves the tool is wired, returns
    # structured_content, and never raises across the boundary.
    (tmp_path / ".planeops").write_text("")
    res = asyncio.run(
        build_server().call_tool("planeops_drift", {"repo": str(tmp_path)})
    )
    assert res.is_error is False
    assert "error" in res.structured_content


def test_an_unmarked_repo_is_a_tool_error_not_a_write(tmp_path):
    # Same refusal rule as the CLI: a directory that is not an instance must
    # error across the boundary (the SDK maps the raise to a protocol-level
    # tool error), never adopt the directory and write state.
    with pytest.raises(Exception, match="not a planeops instance"):
        asyncio.run(
            build_server().call_tool("planeops_observe", {"repo": str(tmp_path)})
        )
    assert not (tmp_path / "observed").exists()


def test_default_repo_resolves_like_the_cli(tmp_path, monkeypatch):
    # An MCP client launches the server from an arbitrary cwd (often "/" or $HOME).
    # With no repo argument, the instance must resolve by the same precedence the
    # CLI uses ($PLANEOPS_INSTANCE here), not by walking up from the client's cwd,
    # which would read the wrong directory and answer "no drift report".
    import json as _json

    inst = tmp_path / "inst"
    (inst / "observed" / "h").mkdir(parents=True)
    (inst / ".planeops").write_text("")
    (inst / "observed" / "h" / "DRIFT.json").write_text(
        _json.dumps({"alert_count": 3, "ts": "t", "summary": {}, "sections": {}})
    )
    monkeypatch.setenv("PLANEOPS_INSTANCE", str(inst))

    class _Plat:
        name = "fake"

        def hostname(self):
            return "h"

        def home(self):
            return tmp_path

    monkeypatch.setattr("planeops.platform.current_platform", lambda: _Plat())
    monkeypatch.chdir(tmp_path)  # a cwd that is NOT the instance

    res = asyncio.run(build_server().call_tool("planeops_status", {}))
    assert res.structured_content.get("alert_count") == 3  # env-resolved instance
