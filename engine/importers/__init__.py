"""Importers seed the registry from hand-maintained manifests. They propose
entries and write nothing without confirmation.

Each importer is a module under `engine/importers/` exposing a module-level
`IMPORTER` that satisfies the `Importer` protocol, discovered by package scan the
same way adapters are. Adding an importer is dropping a module in; the CLI learns
its `kind` from discovery, never from a central edit list (OCP).
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml


@runtime_checkable
class Importer(Protocol):
    """Turns a manifest's text into proposed registry entries. `propose` is pure
    (no writes); `note` is the one-line review header the CLI prints above the
    proposal. `repo_root` lets an importer read instance config (e.g. mapping
    rules); importers that need none ignore it."""

    kind: str

    def propose(self, text: str, repo_root: Path | None) -> list[dict[str, Any]]: ...

    def note(self, path: Path, count: int) -> str: ...


def render_proposal(entries: list[dict[str, Any]]) -> str:
    """The shared YAML rendering of proposed entries (one place, all importers)."""
    return yaml.safe_dump({"entries": entries}, sort_keys=False, allow_unicode=True)


def discover_importers() -> dict[str, Importer]:
    """Every `engine.importers.<mod>` exposing a module-level `IMPORTER`, keyed by
    its `kind`. Mirrors adapter discovery."""
    found: dict[str, Importer] = {}
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"engine.importers.{info.name}")
        importer = getattr(module, "IMPORTER", None)
        if importer is None:
            continue
        if not isinstance(importer, Importer):
            raise TypeError(
                f"engine.importers.{info.name}.IMPORTER does not satisfy "
                "the Importer contract"
            )
        found[importer.kind] = importer
    return found
