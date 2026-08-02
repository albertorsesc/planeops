"""claude-code: MCP servers in `~/.claude.json`; the `claude` binary proves
the client is installed."""

from planeops.adapters.mcp.clients import Client

CLIENT = Client(
    label="claude-code",
    config=".claude.json",
    format="json",
    key="mcpServers",
    binary="claude",
)
