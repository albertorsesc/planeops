"""Load the registry: every `*.yaml` under `registry/`, grouped however the user
likes. Files carry `entries: [...]`; `unmanaged.yaml` carries `globs: [...]` and
`publishers: [...]`, the two ways to say "not mine to govern".
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

_DOC_KEYS = frozenset({"entries", "globs", "publishers"})


@dataclass(frozen=True, slots=True)
class Exemption:
    """One `unmanaged` rule: something on the machine the owner has decided not
    to govern.

    `attested` says where the selector's authority comes from. A glob matches a
    name, and a name is chosen by whatever it names, so a pattern can be entered
    on purpose. A publisher is an identity the OS vouches for (on macOS, the Team
    ID the program is signed with), so nothing can enter it by naming itself.
    That difference is what the triage reads when it decides whether an exemption
    may cover a service that runs at login."""

    value: str
    attested: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Registry:
    entries: tuple[Entry, ...] = ()
    unmanaged: tuple[Exemption, ...] = field(default_factory=tuple)

    def entries_for_host(self, host: str) -> tuple[Entry, ...]:
        return tuple(e for e in self.entries if e.applies_to_host(host))

    def declared_adapters(self) -> set[str]:
        return {e.adapter for e in self.entries}


def load_registry(registry_dir: Path) -> Registry:
    """Read and validate all registry files. Raises SchemaError on the first
    bad entry, with its id, so the user fixes one thing at a time."""
    entries: list[Entry] = []
    unmanaged: list[Exemption] = []
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
            # A typo'd top-level key (`entrys:`) must not make the whole file
            # silently contribute nothing.
            reject_unknown_keys(doc, _DOC_KEYS, path.name)

            for raw in doc.get("entries", []) or []:
                entry = entry_from_dict(raw)
                if entry.id in seen_ids:
                    raise SchemaError(f"{path.name}: duplicate entry id {entry.id!r}")
                seen_ids.add(entry.id)
                entries.append(entry)

            for key, attested in (("globs", False), ("publishers", True)):
                for raw in doc.get(key, []) or []:
                    selector = key[:-1]  # globs -> glob, publishers -> publisher
                    if (
                        not isinstance(raw, dict)
                        or not isinstance(raw.get(selector), str)
                        or not raw[selector]
                    ):
                        raise SchemaError(
                            f"{path.name}: each {selector} must be a mapping with "
                            f"a string {selector!r} key"
                        )
                    unmanaged.append(
                        Exemption(
                            value=raw[selector],
                            attested=attested,
                            reason=raw.get("reason", ""),
                        )
                    )

    return Registry(entries=tuple(entries), unmanaged=tuple(unmanaged))
