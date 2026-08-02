import json
from datetime import datetime

import pytest

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


def test_a_malformed_source_is_loud_not_silently_skipped(tmp_path):
    # A typo'd key in one source used to mean "observe nothing" with no signal;
    # raising here lands in the snapshot's failed-scan alert instead.
    (tmp_path / "instance.yaml").write_text(
        "mcp:\n  sources:\n    - {label: a, paht: ~/x.json, format: json}\n"
    )
    with pytest.raises(ValueError, match="path"):
        load_sources(tmp_path)


def test_a_non_mapping_source_is_loud(tmp_path):
    (tmp_path / "instance.yaml").write_text("mcp:\n  sources:\n    - just-a-string\n")
    with pytest.raises(ValueError, match="mapping"):
        load_sources(tmp_path)


def test_a_typod_optional_key_field_is_loud(tmp_path):
    # `kye:` used to be ignored and `key` defaulted to mcpServers: a source
    # whose servers live under another key silently observed nothing.
    (tmp_path / "instance.yaml").write_text(
        "mcp:\n  sources:\n"
        "    - {label: a, path: ~/x.yaml, format: yaml, kye: servers}\n"
    )
    with pytest.raises(ValueError, match="key"):
        load_sources(tmp_path)


def test_key_must_be_a_string_not_coerced(tmp_path):
    (tmp_path / "instance.yaml").write_text(
        "mcp:\n  sources:\n    - {label: a, path: ~/x.json, format: json, key: 3}\n"
    )
    with pytest.raises(ValueError, match="key"):
        load_sources(tmp_path)


def test_a_corrupt_source_file_is_loud_not_an_empty_scan(tmp_path, fake_platform):
    # A source file that EXISTS but cannot be parsed used to read as {} (its
    # servers just vanished from the snapshot). An absent file stays quiet:
    # the tool may simply not be installed.
    (tmp_path / "instance.yaml").write_text(
        "mcp:\n  sources:\n    - {label: harness, path: ~/.harness.json, format: json}\n"
    )
    (tmp_path / ".harness.json").write_text("{not valid json")
    with pytest.raises(ValueError, match="harness"):
        McpAdapter().observe(_ctx(fake_platform(tmp_path), repo_root=tmp_path))


def test_an_absent_source_file_stays_quiet(tmp_path, fake_platform):
    (tmp_path / "instance.yaml").write_text(
        "mcp:\n  sources:\n    - {label: harness, path: ~/.nope.json, format: json}\n"
    )
    assert McpAdapter().observe(_ctx(fake_platform(tmp_path), repo_root=tmp_path)) == []


def test_a_source_log_template_lands_per_server(tmp_path, fake_platform):
    # A client that keeps per-server logs declares WHERE as a template; the
    # observation resolves it per server so the manifest can know.
    (tmp_path / "instance.yaml").write_text(
        "mcp:\n  sources:\n"
        "    - label: desktop\n"
        "      path: ~/.desktop.json\n"
        "      format: json\n"
        "      logs: ~/Library/Logs/Desk/mcp-server-{name}.log\n"
    )
    (tmp_path / ".desktop.json").write_text(
        json.dumps({"mcpServers": {"context7": {"command": "npx"}}})
    )
    out = McpAdapter().observe(_ctx(fake_platform(tmp_path), repo_root=tmp_path))
    assert out[0].facts["logs"] == ["~/Library/Logs/Desk/mcp-server-context7.log"]


def test_sources_without_a_log_template_carry_no_logs(tmp_path, fake_platform):
    (tmp_path / "instance.yaml").write_text(
        "mcp:\n  sources:\n    - {label: a, path: ~/.a.json, format: json}\n"
    )
    (tmp_path / ".a.json").write_text(
        json.dumps({"mcpServers": {"x": {"command": "npx"}}})
    )
    out = McpAdapter().observe(_ctx(fake_platform(tmp_path), repo_root=tmp_path))
    assert "logs" not in out[0].facts
