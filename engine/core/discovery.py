"""Adapter discovery by package scan.

Every package under `engine/adapters/` that exposes a module-level `ADAPTER`
is registered automatically. Adding an adapter is dropping a directory in; the
core never learns adapter names from a central edit list (SPEC.md decision, OCP).
"""

from __future__ import annotations

import importlib
import pkgutil

import engine.adapters
from engine.core.contracts import Adapter


def discover_adapters() -> dict[str, Adapter]:
    found: dict[str, Adapter] = {}
    for info in pkgutil.iter_modules(engine.adapters.__path__):
        module = importlib.import_module(f"engine.adapters.{info.name}")
        adapter = getattr(module, "ADAPTER", None)
        if adapter is None:
            continue
        if not isinstance(adapter, Adapter):
            raise TypeError(
                f"engine.adapters.{info.name}.ADAPTER does not satisfy the Adapter contract"
            )
        found[adapter.name] = adapter
    return found
