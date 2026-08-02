"""Known-client detection for `plane mcp init`.

The conventions table lives HERE, in the mcp adapter, because vendor knowledge
belongs in extensions, never in the core (the fitness tests hold the core to
that). Each row: where a client keeps its MCP config, how to parse it, and,
when the client has one, its per-server log-file convention. Detection only
reports clients whose config actually exists on this machine; wiring a custom
or unknown client stays a hand edit of `instance.yaml`, same shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# label -> (config path relative to home, format, servers key, logs template)
_KNOWN_CLIENTS: tuple[tuple[str, str, str, str, str | None], ...] = (
    ("claude-code", ".claude.json", "json", "mcpServers", None),
    (
        "claude-desktop",
        "Library/Application Support/Claude/claude_desktop_config.json",
        "json",
        "mcpServers",
        "~/Library/Logs/Claude/mcp-server-{name}.log",
    ),
    ("codex", ".codex/config.toml", "toml", "mcp_servers", None),
    ("cursor", ".cursor/mcp.json", "json", "mcpServers", None),
)


def detect_sources(home: Path) -> list[dict[str, Any]]:
    """Source mappings for every known client whose config exists under `home`."""
    found: list[dict[str, Any]] = []
    for label, rel, fmt, key, logs in _KNOWN_CLIENTS:
        if (home / rel).is_file():
            source: dict[str, Any] = {
                "label": label,
                "path": f"~/{rel}",
                "format": fmt,
                "key": key,
            }
            if logs:
                source["logs"] = logs
            found.append(source)
    return found
