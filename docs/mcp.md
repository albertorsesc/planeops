# MCP: the view and the server

planeops touches MCP twice, in opposite directions: it *observes* the MCP
servers wired into your AI apps, and it can itself be *queried* over MCP by
your assistant. Both are read-only.

## The view: every server, every client, one table

MCP servers exist only inside each AI app's own config file, so the same server
can be wired into one client and missing from another with no way to notice.
`plane observe` reads every configured source and merges servers by name;
`plane mcp` shows the result: which servers exist, which clients have each one
wired, and which are governed by a registry entry.

Sources are configuration, not code: the engine hardcodes no vendor's paths.

```console
$ plane mcp init
```

detects installed known clients (claude-code, claude-desktop, codex, cursor)
and wires their config files as sources. A client counts as installed only when
its binary or app bundle is actually present, so a leftover config from an
uninstalled tool is never wired. Anything custom is one block in
`instance.yaml`:

```yaml
mcp:
  sources:
    - {label: my-gateway, path: ~/.config/gw/servers.json, format: json, key: mcpServers}
```

Formats: `json`, `yaml`, `toml`. A source labeled as a known client inherits
that client's per-server log location automatically. Server `env` blocks are
never recorded: they can hold secrets.

## The server: let your assistant read the plane

Install the extra (`uv tool install "planeops[mcp]"`) and wire `plane-mcp` into
your assistant. It exposes five read-only tools over stdio:

- `planeops_observe`: fresh scan
- `planeops_drift`: the triaged diff
- `planeops_status`: the last drift report, no recompute
- `planeops_mcp`: the server-by-client view above
- `planeops_secrets_list`: the secret names in the store, never a value

Your assistant can answer "what drifted on my machine this week?" and "which
clients have the context7 server wired?" from real state instead of guessing.
There are deliberately no mutation tools: converging stays behind the CLI's
confirmation gate, in your terminal, under your fingers.
