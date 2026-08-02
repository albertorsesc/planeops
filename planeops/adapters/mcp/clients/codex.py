"""codex: MCP servers as `[mcp_servers.<name>]` tables in TOML; the `codex`
binary proves the client is installed (its config dir is known to outlive it)."""

from planeops.adapters.mcp.clients import Client

CLIENT = Client(
    label="codex",
    config=".codex/config.toml",
    format="toml",
    key="mcp_servers",
    binary="codex",
)
