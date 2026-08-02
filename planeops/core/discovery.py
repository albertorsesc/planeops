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
import re
from types import ModuleType

import planeops.adapters
from planeops.core.contracts import Adapter

# Implementation names feed `<adapter>/<native_id>` observation keys (split at
# the FIRST slash; native_ids may themselves contain slashes) and unmanaged-glob
# matching, so the grammar is load-bearing: enforced at the seam, before any
# name can ship in an external package.
_NAME_RE = re.compile(r"^[a-z0-9_.-]+$")


def validate_seam_name(name: object, *, context: str) -> str:
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise TypeError(
            f"{context}: implementation name {name!r} must match [a-z0-9_.-]+ "
            "(no slashes: names prefix '<name>/<native_id>' keys)"
        )
    return name


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
        found[
            validate_seam_name(
                getattr(candidate, key), context=f"{package.__name__}.{info.name}"
            )
        ] = candidate
    return found


def discover_adapters() -> dict[str, Adapter]:
    return discover(
        planeops.adapters,
        "ADAPTER",
        Adapter,  # type: ignore[type-abstract]  # isinstance-only, see discover()
    )
