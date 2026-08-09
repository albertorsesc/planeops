"""Known MCP clients: one module per client, discovered, never listed.

The same seam pattern as adapters/stores/schedulers, one level down: each
module here exposes a `CLIENT` declaring where that client keeps its MCP
config, how to parse it, its per-server log convention when it has one, and
how to tell the client itself is installed. That last part matters: a config
directory can outlive its uninstalled client, and wiring a remnant would make
the cross-client view claim servers are "wired in" a tool that no longer
exists. Adding a client is dropping a module in; nothing central changes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# A scope reader: given the client's parsed main config and the home dir,
# yields (scope-label, servers-mapping) pairs BEYOND the main key: e.g. a
# per-project section, or a per-repo config file the main config points at.
ScopeReader = Callable[[dict[str, Any], Path], list[tuple[str, dict[str, Any]]]]

# A server remover: a pure transform (data, key, name) -> new data with that
# server's block gone from the mapping under `key`. Declared by a leaf only
# when this client's config format supports a faithful rewrite; a client
# without one is simply not writable, and plan says so instead of guessing.
ServerRemover = Callable[[dict[str, Any], str, str], dict[str, Any]]


@runtime_checkable
class KnownClient(Protocol):
    label: str
    config: str  # config path relative to home
    format: str
    key: str
    logs: str | None  # per-server log template ({name}), or None
    binary: str | None  # installed-probe: a binary expected on PATH
    app: str | None  # installed-probe: an app bundle name
    scopes: ScopeReader | None  # extra wiring scopes, or None
    remove_server: ServerRemover | None  # write capability, or None


@dataclass(frozen=True, slots=True)
class Client:
    """The declarative shape each leaf instantiates as `CLIENT`."""

    label: str
    config: str
    format: str
    key: str
    logs: str | None = None
    binary: str | None = None
    app: str | None = None
    scopes: ScopeReader | None = None
    remove_server: ServerRemover | None = None


def discover_clients() -> dict[str, KnownClient]:
    """Every `planeops.adapters.mcp.clients.<mod>` exposing a `CLIENT`."""
    import planeops.adapters.mcp.clients as pkg
    from planeops.core.discovery import discover

    return discover(
        pkg,
        "CLIENT",
        KnownClient,  # type: ignore[type-abstract]  # isinstance-only
        key="label",
    )
