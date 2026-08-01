"""Discovery by package scan: the one mechanism behind every extension seam.

A seam is a package whose modules each expose one well-known module-level
attribute (`ADAPTER`, `IMPORTER`, `PLATFORM`, `SCHEDULER`, `STORE`) satisfying
that seam's contract. `discover()` is the shared scan; each seam wraps it in a
one-liner. Adding an implementation is dropping a module in; nothing ever learns
its name from a central edit list (SPEC.md decision, OCP), and the scan is
written once instead of five times.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

import engine.adapters
from engine.core.contracts import Adapter


def discover[T](
    package: ModuleType, attr: str, contract: type[T], *, key: str = "name"
) -> dict[str, T]:
    """Scan `package` for modules exposing `attr`, verify each against
    `contract`, and return them keyed by their `key` attribute. A module without
    the attribute is simply not an implementation; one with a non-conforming
    attribute is a loud TypeError, never a silent skip.

    `contract` is a runtime_checkable Protocol used only for isinstance; mypy's
    type-abstract check guards instantiation we never do (and its redundant-cast
    check rejects the cast workaround), so call sites carry the one sanctioned
    `type: ignore[type-abstract]` in this codebase, justified here once."""
    found: dict[str, T] = {}
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        candidate = getattr(module, attr, None)
        if candidate is None:
            continue
        if not isinstance(candidate, contract):
            raise TypeError(
                f"{package.__name__}.{info.name}.{attr} does not satisfy "
                f"the {contract.__name__} contract"
            )
        found[getattr(candidate, key)] = candidate
    return found


def discover_adapters() -> dict[str, Adapter]:
    return discover(
        engine.adapters,
        "ADAPTER",
        Adapter,  # type: ignore[type-abstract]  # isinstance-only, see discover()
    )
