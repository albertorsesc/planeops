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
never hardcodes where any particular tool keeps its config. Env values are never
recorded, they can hold secrets.

The write side (planeops/adapters/mcp/write.py) converges one case: a retired or
purge entry still wired in a client's user scope gets its block removed, behind
apply's confirm gate and an explicit `mcp.manage: true` opt-in in instance.yaml.
Wiring a server INTO a client stays out: a server block carries env values the
registry must never hold in plaintext.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from planeops.config import section as instance_section
from planeops.core.contracts import Change, Ctx, Observed, Result
from planeops.core.schema import Entry, reject_unknown_keys
from planeops.providers import yaml


@dataclass(frozen=True, slots=True)
class McpSource:
    label: str
    path: str
    format: str  # "json", "yaml", or "toml"
    key: str  # the mapping key holding the servers, e.g. "mcpServers"
    # Optional template for this client's per-server log location, with {name}
    # standing for the server name (e.g. "~/Library/Logs/X/mcp-{name}.log").
    logs: str | None = None


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


_SOURCE_KEYS = frozenset({"label", "path", "format", "key", "logs"})


def _known_client(label: str) -> Any:
    """The discovered known client with this label, if any. Lazy import: the
    clients seam pulls in discovery machinery this module should not load
    unless a source actually references a known client."""
    from planeops.adapters.mcp.clients import discover_clients

    return discover_clients().get(label)


def _known_client_logs(label: str) -> str | None:
    client = _known_client(label)
    return client.logs if client else None


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
        fmt_val = item.get("format")
        if fmt_val not in ("json", "yaml", "toml"):
            raise ValueError(
                f"mcp.sources[{i}] format must be json, yaml, or toml (got {fmt_val!r})"
            )
        logs_t = item.get("logs")
        if logs_t is not None and (not isinstance(logs_t, str) or not logs_t):
            raise ValueError(
                f"mcp.sources[{i}] logs must be a non-empty string template "
                f"(got {logs_t!r})"
            )
        label = _source_str(item, "label", i)
        sources.append(
            McpSource(
                label=label,
                path=_source_str(item, "path", i),
                format=_source_str(item, "format", i),
                key=_source_str(item, "key", i, default="mcpServers"),
                # Derived default: a source labeled as a discovered known
                # client inherits that client's conventions at read time, so
                # templates upgrade with the tool and config stays minimal.
                # An explicit value in instance.yaml always wins.
                logs=logs_t if logs_t is not None else _known_client_logs(label),
            )
        )
    return sources


def resolve_path(path_str: str, home: Path) -> Path:
    """A source path resolved against the platform's home, not the process's,
    so a fake platform in tests confines every read to its own tree."""
    if path_str == "~":
        return home
    if path_str.startswith("~/"):
        return home / path_str[2:]
    return Path(path_str)


def _parse_source(source: McpSource, home: Path) -> dict[str, Any] | None:
    """The source file parsed to a mapping, or None when absent (the tool may
    simply not be installed on this machine: quiet)."""
    path = resolve_path(source.path, home)
    if not path.is_file():
        return None
    try:
        text = path.read_text()
        if source.format == "yaml":
            data = yaml.load(text)
        elif source.format == "toml":
            data = tomllib.loads(text)
        else:
            data = json.loads(text)
    except (
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
        ValueError,
        yaml.ParseError,
        OSError,
    ) as exc:
        # A file that EXISTS but cannot be read or parsed must not quietly
        # observe as "no servers": raise into the failed-scan alert.
        raise ValueError(
            f"mcp source {source.label!r}: cannot read {path}: {exc}"
        ) from exc
    return data if isinstance(data, dict) else {}


class McpAdapter:
    name = "mcp"
    domains: tuple[str, ...] = ("mcp-server",)
    # Converge order: wiring is config, alongside chezmoi's slot.
    default_phase = 3

    def __init__(self, sources: list[McpSource] | None = None):
        self._sources_override = sources

    def _sources(self, ctx: Ctx) -> list[McpSource]:
        if self._sources_override is not None:
            return self._sources_override
        return load_sources(ctx.repo_root)

    def plan(self, entry: Entry, obs: Observed | None, ctx: Ctx) -> list[Change]:
        from planeops.adapters.mcp.write import plan_unwire

        if obs is None:
            return []  # nothing observed wired; nothing to remove
        return plan_unwire(entry, obs.facts, ctx, self._sources(ctx))

    def execute(self, change: Change, ctx: Ctx) -> Result:
        from planeops.adapters.mcp.write import execute_unwire

        if change.action.get("op") != "unwire":
            return Result(
                ok=False, detail=f"unknown mcp op {change.action.get('op')!r}"
            )
        return execute_unwire(change, ctx)

    def observe(self, ctx: Ctx) -> list[Observed]:
        sources = self._sources(ctx)
        home = ctx.platform.home()

        merged: dict[str, dict[str, Any]] = {}

        def _merge(label: str, source: McpSource, servers: object, scope: str) -> None:
            for server_name, meta in servers_from_mapping(servers).items():
                entry = merged.setdefault(
                    server_name,
                    {"sources": set(), "wirings": set(), "command": "", "logs": set()},
                )
                entry["sources"].add(label)
                # The structured twin of the display label: consumers that must
                # DECIDE something (which file a write may touch) read this,
                # never the label string, whose format is presentation.
                entry["wirings"].add((source.label, scope))
                if not entry["command"] and meta["command"]:
                    entry["command"] = meta["command"]
                if source.logs:
                    entry["logs"].add(source.logs.format(name=server_name))

        for source in sources:
            data = _parse_source(source, home)
            if data is None:
                continue
            _merge(source.label, source, data.get(source.key), "user")
            # A known client can wire servers in scopes beyond its main key
            # (a per-project section, a committed repo file); each surfaces
            # under its own scoped label so the view can tell "everywhere"
            # from "only in this project".
            client = _known_client(source.label)
            if client is not None and client.scopes is not None:
                for scope, mapping in client.scopes(data, home):
                    _merge(f"{source.label} {scope}", source, mapping, scope)

        return [
            Observed(
                adapter=self.name,
                native_id=server_name,
                facts={
                    "sources": sorted(merged[server_name]["sources"]),
                    "wirings": [
                        {"client": c, "scope": s}
                        for c, s in sorted(merged[server_name]["wirings"])
                    ],
                    "command": merged[server_name]["command"],
                    **(
                        {"logs": sorted(merged[server_name]["logs"])}
                        if merged[server_name]["logs"]
                        else {}
                    ),
                },
                version=None,
            )
            for server_name in sorted(merged)
        ]


ADAPTER = McpAdapter()
