"""mcp adapter (MCP servers across runtimes).

MCP servers get wired into several tools independently (a coding harness, a desktop
app, a gateway, ...), each in its own config file. Nobody keeps a single list, so a
server can live in one tool and not another with no way to notice.

observe reads every configured source, merges servers by name, and records which
sources each is wired into (`facts.sources`). A server that shows only one source
is a candidate to reuse in the others.

This adapter names no specific tool. The sources are configuration: a list of
`{label, path, format, key}` under the `mcp.sources` key of `instance.yaml` at the
instance root (see `planeops/instance.example.yaml`). The engine reads that list; it
never hardcodes where any particular tool keeps its config. Observe-only: wiring a
server into a tool means writing that tool's config, deferred past v1. Env values
are never recorded, they can hold secrets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from planeops.config import section as instance_section
from planeops.core.contracts import Ctx, Observed
from planeops.core.schema import reject_unknown_keys


@dataclass(frozen=True, slots=True)
class McpSource:
    label: str
    path: str
    format: str  # "json" or "yaml"
    key: str  # the mapping key holding the servers, e.g. "mcpServers"


def servers_from_mapping(servers: object) -> dict[str, dict[str, Any]]:
    """Normalize a servers mapping to `{name: {command}}`. Env is deliberately
    dropped: it can hold secret values."""
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(servers, dict):
        return out
    for name, cfg in servers.items():
        if not isinstance(name, str):
            continue
        command = ""
        if isinstance(cfg, dict) and isinstance(cfg.get("command"), str):
            command = cfg["command"]
        out[name] = {"command": command}
    return out


_SOURCE_KEYS = frozenset({"label", "path", "format", "key"})


def _source_str(
    item: dict[str, Any], field_name: str, i: int, default: str | None = None
) -> str:
    value = item.get(field_name, default)
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"mcp.sources[{i}] needs a string {field_name!r} "
            f"(got {value!r}); check instance.yaml for a typo"
        )
    return value


def load_sources(repo_root: Path | None) -> list[McpSource]:
    """Read the source list from `instance.yaml`'s `mcp.sources`. Missing file,
    root, or section yields no sources (the adapter then observes nothing): the
    feature is opt-in. A PRESENT but malformed source raises instead of being
    silently skipped: the raise lands in the snapshot's failed-scan alert, so a
    typo'd key can never quietly mean "observe nothing"."""
    raw = instance_section(repo_root, "mcp").get("sources")
    if not isinstance(raw, list):
        return []
    sources: list[McpSource] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"mcp.sources[{i}] must be a mapping, got {item!r}")
        reject_unknown_keys(item, _SOURCE_KEYS, f"mcp.sources[{i}]")
        sources.append(
            McpSource(
                label=_source_str(item, "label", i),
                path=_source_str(item, "path", i),
                format=_source_str(item, "format", i),
                key=_source_str(item, "key", i, default="mcpServers"),
            )
        )
    return sources


def _resolve(path_str: str, home: Path) -> Path:
    if path_str == "~":
        return home
    if path_str.startswith("~/"):
        return home / path_str[2:]
    return Path(path_str)


def _read_source(source: McpSource, home: Path) -> dict[str, dict[str, Any]]:
    path = _resolve(source.path, home)
    if not path.is_file():
        # The tool may simply not be installed on this machine: quiet.
        return {}
    try:
        text = path.read_text()
        data = yaml.safe_load(text) if source.format == "yaml" else json.loads(text)
    except (json.JSONDecodeError, ValueError, yaml.YAMLError, OSError) as exc:
        # A file that EXISTS but cannot be read or parsed must not quietly
        # observe as "no servers": raise into the failed-scan alert.
        raise ValueError(
            f"mcp source {source.label!r}: cannot read {path}: {exc}"
        ) from exc
    servers = data.get(source.key) if isinstance(data, dict) else None
    return servers_from_mapping(servers)


class McpAdapter:
    name = "mcp"
    domains: tuple[str, ...] = ("mcp-server",)

    def __init__(self, sources: list[McpSource] | None = None):
        self._sources_override = sources

    def observe(self, ctx: Ctx) -> list[Observed]:
        sources = self._sources_override
        if sources is None:
            sources = load_sources(ctx.repo_root)
        home = ctx.platform.home()

        merged: dict[str, dict[str, Any]] = {}
        for source in sources:
            for server_name, meta in _read_source(source, home).items():
                entry = merged.setdefault(server_name, {"sources": [], "command": ""})
                entry["sources"].append(source.label)
                if not entry["command"] and meta["command"]:
                    entry["command"] = meta["command"]

        return [
            Observed(
                adapter=self.name,
                native_id=server_name,
                facts={
                    "sources": sorted(merged[server_name]["sources"]),
                    "command": merged[server_name]["command"],
                },
                version=None,
            )
            for server_name in sorted(merged)
        ]


ADAPTER = McpAdapter()
