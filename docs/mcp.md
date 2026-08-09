# MCP: the view and the server

planeops touches MCP twice, in opposite directions: it *observes* the MCP
servers wired into your AI apps, and it can itself be *queried* over MCP by
your assistant. Observation never writes; the one write the adapter offers,
unwiring a retired server, is opt-in and gated below.

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

A known client's extra wiring scopes are read too, from its own config, with
no filesystem search: for claude-code that means each `projects.<dir>`
section (`claude mcp add`'s default, private to that directory) and each
committed `.mcp.json` inside those directories. Scoped wirings show under
their own label, `claude-code project:~/x` or `claude-code repo:~/x`, so the
view tells "wired everywhere" from "wired only in one project".

## Unwiring: retire a server and let apply remove it

Retiring an MCP server in the registry declares it should be gone; the wiring
in each client's config is the leftover. With the opt-in set:

```yaml
mcp:
  manage: true
  sources:
    - ...
```

`plane apply` proposes one change per retired-but-still-wired server, naming
every client file it would edit, and removes the server's block after your
`y`. The write is deliberately paranoid, because these files belong to other
programs:

- Only user-scope wirings in configured sources are touched. Project- and
  repo-scoped wirings are listed as skipped: remove those where they live.
- The file is re-read at execution and refused if it changed since the
  preview, byte-for-byte, digest-checked.
- Only JSON files whose formatting round-trips exactly are edited; a config
  planeops cannot reproduce byte-identically is refused, never rewritten.
- The removed block (env included) is backed up first, to
  `~/.local/state/planeops/backups/`, mode 0600, so an unwire is undoable.
- The write is atomic, follows symlinks to the real file, and preserves its
  permissions. Everything except the removed block stays byte-identical.

Previews, results, and the journal name servers and paths only, never `env`
values. A client already running keeps serving the server until restarted.
Wiring servers *in* stays manual for now: `env` blocks carry secrets, and
writing those from a registry needs the secrets seam, not a config editor.

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
