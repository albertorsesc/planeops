"""Load the registry: every `*.yaml` under `registry/`, grouped however the user
likes. Files carry `entries: [...]`; `unmanaged.yaml` carries `globs: [...]`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from planeops.core.schema import (
    Entry,
    SchemaError,
    entry_from_dict,
    reject_unknown_keys,
)
from planeops.providers import yaml

_DOC_KEYS = frozenset({"entries", "globs"})


@dataclass(frozen=True, slots=True)
class UnmanagedGlob:
    glob: str
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Registry:
    entries: tuple[Entry, ...] = ()
    unmanaged: tuple[UnmanagedGlob, ...] = field(default_factory=tuple)

    def entries_for_host(self, host: str) -> tuple[Entry, ...]:
        return tuple(e for e in self.entries if e.applies_to_host(host))

    def declared_adapters(self) -> set[str]:
        return {e.adapter for e in self.entries}


def load_registry(registry_dir: Path) -> Registry:
    """Read and validate all registry files. Raises SchemaError on the first
    bad entry, with its id, so the user fixes one thing at a time."""
    entries: list[Entry] = []
    unmanaged: list[UnmanagedGlob] = []
    seen_ids: set[str] = set()

    if not registry_dir.is_dir():
        return Registry()

    for path in sorted(registry_dir.glob("*.yaml")):
        docs = yaml.load_all(path.read_text()) or []
        for doc in docs:
            if not doc:
                continue
            if not isinstance(doc, dict):
                raise SchemaError(f"{path.name}: top-level document must be a mapping")
            # A typo'd top-level key (`entrys:`) used to make the whole file
            # silently contribute nothing.
            reject_unknown_keys(doc, _DOC_KEYS, path.name)

            for raw in doc.get("entries", []) or []:
                entry = entry_from_dict(raw)
                if entry.id in seen_ids:
                    raise SchemaError(f"{path.name}: duplicate entry id {entry.id!r}")
                seen_ids.add(entry.id)
                entries.append(entry)

            for raw in doc.get("globs", []) or []:
                if (
                    not isinstance(raw, dict)
                    or not isinstance(raw.get("glob"), str)
                    or not raw["glob"]
                ):
                    raise SchemaError(
                        f"{path.name}: each glob must be a mapping with a "
                        "string 'glob' key"
                    )
                unmanaged.append(
                    UnmanagedGlob(glob=raw["glob"], reason=raw.get("reason", ""))
                )

    return Registry(entries=tuple(entries), unmanaged=tuple(unmanaged))
