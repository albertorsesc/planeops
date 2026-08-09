"""claude-code: MCP servers in `~/.claude.json`; the `claude` binary proves
the client is installed.

Beyond the user-scope `mcpServers` key, claude-code wires servers in two more
scopes, both reachable from its own config: `projects.<dir>.mcpServers` (the
`claude mcp add` default, private to this user and directory) and a committed
`.mcp.json` inside a project (shared with whoever clones the repo). The
`projects` section enumerates every directory the client has opened, so both
scopes are read without any filesystem search.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from planeops.adapters.mcp.clients import Client
from planeops.adapters.mcp.clients.flatjson import remove_server


def _short(path: str, home: Path) -> str:
    p = Path(path)
    try:
        return f"~/{p.relative_to(home)}"
    except ValueError:
        return path


def _scoped_servers(
    data: dict[str, Any], home: Path
) -> list[tuple[str, dict[str, Any]]]:
    """(scope-label, servers) pairs: `project:<dir>` for the private
    per-directory scope, `repo:<dir>` for a committed `.mcp.json`. A repo file
    that exists but cannot be parsed raises, landing as a failed-scan alert,
    the same loud rule every mcp source follows."""
    out: list[tuple[str, dict[str, Any]]] = []
    projects = data.get("projects")
    if not isinstance(projects, dict):
        return out
    for path in sorted(p for p in projects if isinstance(p, str)):
        label = _short(path, home)
        cfg = projects[path]
        servers = cfg.get("mcpServers") if isinstance(cfg, dict) else None
        if isinstance(servers, dict) and servers:
            out.append((f"project:{label}", servers))
        repo_file = Path(path) / ".mcp.json"
        if repo_file.is_file():
            try:
                repo_data = json.loads(repo_file.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                raise ValueError(f"cannot read {repo_file}: {exc}") from exc
            repo_servers = (
                repo_data.get("mcpServers") if isinstance(repo_data, dict) else None
            )
            if isinstance(repo_servers, dict) and repo_servers:
                out.append((f"repo:{label}", repo_servers))
    return out


CLIENT = Client(
    label="claude-code",
    config=".claude.json",
    format="json",
    key="mcpServers",
    binary="claude",
    scopes=_scoped_servers,
    remove_server=remove_server,
)
