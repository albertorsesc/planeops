"""The clients seam: discovered, contract-satisfying, one module each."""

from planeops.adapters.mcp.clients import KnownClient, discover_clients


def test_clients_discovered_and_satisfy_the_contract():
    clients = discover_clients()
    assert set(clients) >= {"claude-code", "claude-desktop", "codex", "cursor"}
    for label, c in clients.items():
        assert isinstance(c, KnownClient)
        assert c.label == label
        assert c.binary or c.app, f"{label} has no installed-probe"
