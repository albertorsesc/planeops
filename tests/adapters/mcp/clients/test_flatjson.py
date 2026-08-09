"""The shared flat-JSON editor: pure, order-preserving, reference-carrying."""

import pytest

from planeops.adapters.mcp.clients.flatjson import remove_server


def test_remove_is_pure_and_preserves_order_and_env():
    env = {"API_KEY": "sk-secret"}
    data = {
        "before": 1,
        "mcpServers": {"a": {"command": "npx"}, "b": {"env": env}, "c": {}},
        "after": 2,
    }
    out = remove_server(data, "mcpServers", "a")
    assert list(out) == ["before", "mcpServers", "after"]  # top-level order kept
    assert list(out["mcpServers"]) == ["b", "c"]
    assert out["mcpServers"]["b"]["env"] is env  # value object untouched
    assert data["mcpServers"] == {"a": {"command": "npx"}, "b": {"env": env}, "c": {}}


def test_remove_absent_name_raises():
    # The caller verified the block against a digest; absence means the file
    # changed underneath, and silence would hide that.
    with pytest.raises(KeyError):
        remove_server({"mcpServers": {}}, "mcpServers", "ghost")
