from planeops.adapters.mcp.clients.codex import CLIENT


def test_declaration_is_complete():
    assert CLIENT.config and CLIENT.format in ("json", "yaml", "toml") and CLIENT.key
