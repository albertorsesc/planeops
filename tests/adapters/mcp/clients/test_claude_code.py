import pytest

from planeops.adapters.mcp.clients.claude_code import CLIENT


def test_declaration_is_complete():
    assert CLIENT.config and CLIENT.format in ("json", "yaml", "toml") and CLIENT.key


# ---- project scopes: read from the client's own config, no filesystem search ----


def test_scoped_servers_reads_project_and_repo_scopes(tmp_path):
    proj = tmp_path / "Projects" / "life-chess"
    proj.mkdir(parents=True)
    (proj / ".mcp.json").write_text(
        '{"mcpServers": {"expo": {"command": "npx expo-mcp"}}}'
    )
    data = {
        "mcpServers": {"user-scope": {"command": "u"}},
        "projects": {
            str(proj): {"mcpServers": {"seq": {"command": "npx seq"}}},
            str(tmp_path / "empty-proj"): {"mcpServers": {}},
        },
    }
    out = CLIENT.scopes(data, tmp_path)
    assert out == [
        (f"project:~/{proj.relative_to(tmp_path)}", {"seq": {"command": "npx seq"}}),
        (f"repo:~/{proj.relative_to(tmp_path)}", {"expo": {"command": "npx expo-mcp"}}),
    ]


def test_scoped_servers_quiet_without_projects(tmp_path):
    assert CLIENT.scopes({"mcpServers": {"a": {}}}, tmp_path) == []


def test_scoped_servers_outside_home_keeps_the_full_path(tmp_path):
    data = {"projects": {"/opt/elsewhere": {"mcpServers": {"x": {"command": "c"}}}}}
    out = CLIENT.scopes(data, tmp_path)
    assert out == [("project:/opt/elsewhere", {"x": {"command": "c"}})]


def test_a_malformed_repo_mcp_json_is_loud(tmp_path):
    proj = tmp_path / "repo"
    proj.mkdir()
    (proj / ".mcp.json").write_text("{ broken")
    data = {"projects": {str(proj): {}}}
    with pytest.raises(ValueError, match="cannot read"):
        CLIENT.scopes(data, tmp_path)
