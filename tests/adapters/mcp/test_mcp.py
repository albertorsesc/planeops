import json
from datetime import datetime

from planeops.adapters.mcp import (
    ADAPTER,
    McpAdapter,
    McpSource,
    load_sources,
    servers_from_mapping,
)
from planeops.core.contracts import Ctx, can_apply


def _ctx(platform, repo_root=None):
    return Ctx(
        platform=platform,
        host="testhost",
        now=datetime(2026, 7, 27),
        repo_root=repo_root,
    )


def _sources():
    # Generic labels/paths; the adapter names no real tool.
    return [
        McpSource("harness", "~/.harness.json", "json", "mcpServers"),
        McpSource("desktop", "~/Library/App/desktop.json", "json", "mcpServers"),
        McpSource("gateway", "~/.gateway.yaml", "yaml", "mcp_servers"),
    ]


def _write_full_machine(home):
    # filesystem -> harness only; fetch -> harness + desktop (with a secret env
    # that must never surface); memory -> desktop + gateway; github -> gateway.
    (home / ".harness.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "filesystem": {"command": "npx"},
                    "fetch": {"command": "uvx", "env": {"API_TOKEN": "sk-secret-123"}},
                }
            }
        )
    )
    d = home / "Library" / "App"
    d.mkdir(parents=True, exist_ok=True)
    (d / "desktop.json").write_text(
        json.dumps(
            {"mcpServers": {"fetch": {"command": "uvx"}, "memory": {"command": "npx"}}}
        )
    )
    (home / ".gateway.yaml").write_text(
        "mcp_servers:\n  memory:\n    command: node\n  github:\n    command: docker\n"
    )


# ---- servers_from_mapping (pure) -----------------------------------------


def test_servers_from_mapping_extracts_command():
    m = servers_from_mapping({"a": {"command": "npx"}, "b": {"command": "uvx"}})
    assert m == {"a": {"command": "npx"}, "b": {"command": "uvx"}}


def test_servers_from_mapping_tolerates_non_dicts():
    assert servers_from_mapping(None) == {}
    assert servers_from_mapping("nope") == {}
    assert servers_from_mapping({"a": "not-a-dict"}) == {"a": {"command": ""}}


# ---- observe / cross-source merge ----------------------------------------


def test_observe_merges_servers_across_sources(tmp_path, fake_platform):
    _write_full_machine(tmp_path)
    out = {
        o.native_id: o
        for o in McpAdapter(sources=_sources()).observe(_ctx(fake_platform(tmp_path)))
    }
    assert set(out) == {"filesystem", "fetch", "memory", "github"}
    assert out["filesystem"].facts["sources"] == ["harness"]
    assert out["fetch"].facts["sources"] == ["desktop", "harness"]
    assert out["memory"].facts["sources"] == ["desktop", "gateway"]
    assert out["github"].facts["sources"] == ["gateway"]
    assert out["fetch"].key == "mcp/fetch"


def test_observe_records_command_but_never_env_values(tmp_path, fake_platform):
    _write_full_machine(tmp_path)
    out = {
        o.native_id: o
        for o in McpAdapter(sources=_sources()).observe(_ctx(fake_platform(tmp_path)))
    }
    assert out["fetch"].facts["command"] == "uvx"
    assert "env" not in out["fetch"].facts
    assert "sk-secret-123" not in json.dumps(out["fetch"].to_dict())


def test_missing_sources_are_empty_not_error(tmp_path, fake_platform):
    assert McpAdapter(sources=_sources()).observe(_ctx(fake_platform(tmp_path))) == []


def test_one_broken_source_does_not_sink_the_others(tmp_path, fake_platform):
    (tmp_path / ".harness.json").write_text("{ not json")
    d = tmp_path / "Library" / "App"
    d.mkdir(parents=True)
    (d / "desktop.json").write_text(
        json.dumps({"mcpServers": {"memory": {"command": "npx"}}})
    )
    out = {
        o.native_id: o
        for o in McpAdapter(sources=_sources()).observe(_ctx(fake_platform(tmp_path)))
    }
    assert set(out) == {"memory"}


def test_mcp_is_observe_only():
    # wiring an MCP into a tool means writing its config; deferred past v1.
    assert not can_apply(ADAPTER)


# ---- config-driven sources (no tool names in the engine) -----------------


def test_load_sources_reads_the_source_list(tmp_path):
    (tmp_path / "instance.yaml").write_text(
        "mcp:\n"
        "  sources:\n"
        "    - label: harness\n"
        "      path: ~/.harness.json\n"
        "      format: json\n"
        "      key: mcpServers\n"
    )
    sources = load_sources(tmp_path)
    assert sources == [McpSource("harness", "~/.harness.json", "json", "mcpServers")]


def test_load_sources_missing_file_is_empty():
    assert load_sources(None) == []


def test_default_adapter_loads_sources_from_config(tmp_path, fake_platform):
    # home and instance root both at tmp_path for the test
    (tmp_path / "instance.yaml").write_text(
        "mcp:\n"
        "  sources:\n"
        "    - label: harness\n"
        "      path: ~/.harness.json\n"
        "      format: json\n"
        "      key: mcpServers\n"
    )
    (tmp_path / ".harness.json").write_text(
        json.dumps({"mcpServers": {"filesystem": {"command": "npx"}}})
    )
    out = McpAdapter().observe(_ctx(fake_platform(tmp_path), repo_root=tmp_path))
    assert [o.native_id for o in out] == ["filesystem"]
    assert out[0].facts["sources"] == ["harness"]
