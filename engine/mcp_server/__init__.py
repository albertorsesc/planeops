"""tarmac's own MCP server: an optional, read-only transport over the CLI verbs.

Distinct from the `mcp` *adapter* (engine/adapters/mcp), which observes OTHER tools'
MCP wirings. This package lets an AI assistant ask "what's on my machine?" and
"what's drifted?" by calling the same run_observe / run_drift the CLI uses, and
never re-implements triage. Read-only by design: no tool here mutates anything.

Requires the optional `mcp` dependency (`pip install tarmac[mcp]`); the core CLI
never imports this package, so a plain install carries no MCP dependency. The
`tools` module has no `mcp` import and holds the actual logic; `server` is the thin
MCPServer wiring.
"""
