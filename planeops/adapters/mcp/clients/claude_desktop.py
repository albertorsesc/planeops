"""claude-desktop: MCP servers in the app's config; per-server logs under
`~/Library/Logs/Claude/`; the app bundle proves the client is installed."""

from planeops.adapters.mcp.clients import Client
from planeops.adapters.mcp.clients.flatjson import remove_server

CLIENT = Client(
    label="claude-desktop",
    config="Library/Application Support/Claude/claude_desktop_config.json",
    format="json",
    key="mcpServers",
    logs="~/Library/Logs/Claude/mcp-server-{name}.log",
    app="Claude.app",
    remove_server=remove_server,
)
