"""cursor: MCP servers in `~/.cursor/mcp.json`; the app bundle proves the
client is installed (its config dir is known to outlive it)."""

from planeops.adapters.mcp.clients import Client
from planeops.adapters.mcp.clients.flatjson import remove_server

CLIENT = Client(
    label="cursor",
    config=".cursor/mcp.json",
    format="json",
    key="mcpServers",
    app="Cursor.app",
    remove_server=remove_server,
)
