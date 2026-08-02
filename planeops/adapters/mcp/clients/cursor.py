"""cursor: MCP servers in `~/.cursor/mcp.json`; the app bundle proves the
client is installed (its config dir is known to outlive it)."""

from planeops.adapters.mcp.clients import Client

CLIENT = Client(
    label="cursor",
    config=".cursor/mcp.json",
    format="json",
    key="mcpServers",
    app="Cursor.app",
)
