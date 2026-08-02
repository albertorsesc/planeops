"""Importers seed the registry from hand-maintained manifests. They propose
entries and write nothing without confirmation.

Each importer is a module under `planeops/importers/` exposing a module-level
`IMPORTER` that satisfies the `Importer` protocol, discovered by package scan the
same way adapters are. Adding an importer is dropping a module in; the CLI learns
its `kind` from discovery, never from a central edit list (OCP).
"""

from __future__ import annotations

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


def render_entry(entry: dict[str, Any]) -> str:
    """One entry as a document-style list item, indented under `entries:`."""
    body = yaml.safe_dump([entry], sort_keys=False, allow_unicode=True)
    return "\n".join(f"  {line}" if line else "" for line in body.rstrip().split("\n"))


def render_proposal(entries: list[dict[str, Any]]) -> str:
    """The shared YAML rendering of proposed entries (one place, all importers).
    Registry files are documents humans edit: one blank line between entries."""
    if not entries:
        return "entries: []\n"
    return "entries:\n" + "\n\n".join(render_entry(e) for e in entries) + "\n"


def write_proposal(
    entries: list[dict[str, Any]],
    repo_root: Path,
    *,
    filename: str = "imported.yaml",
) -> tuple[Path, int]:
    """Land `entries` in `<repo_root>/registry/<filename>`, merging with any already
    there (de-duping by id), and return (path, total entries in the file). Entries are
    expected pre-deduped against the declared registry; this only guards against
    duplicates within the target file so a re-run is idempotent. The file is separate
    from hand-curated registry files, so a user prunes it without losing their edits."""
    from planeops.core.statefile import atomic_write

    target = repo_root / "registry" / filename
    existing: list[dict[str, Any]] = []
    text = ""
    if target.is_file():
        text = target.read_text()
        doc = yaml.safe_load(text) or {}
        if isinstance(doc, dict) and isinstance(doc.get("entries"), list):
            existing = [e for e in doc["entries"] if isinstance(e, dict)]
    seen = {e.get("id") for e in existing}
    fresh = [e for e in entries if e.get("id") not in seen]
    target.parent.mkdir(parents=True, exist_ok=True)
    if not text.strip():
        atomic_write(target, render_proposal(fresh))
    elif fresh:
        # Append ONLY the new entries as text: the existing body (and any
        # comments or pruning marks the user added) is never re-dumped.
        appended = "\n\n".join(render_entry(e) for e in fresh)
        atomic_write(target, text.rstrip("\n") + "\n\n" + appended + "\n")
    return target, len(existing) + len(fresh)


def discover_importers() -> dict[str, Importer]:
    """Every `planeops.importers.<mod>` exposing a module-level `IMPORTER`, keyed
    by its `kind`. The shared package-scan seam."""
    import planeops.importers
    from planeops.core.discovery import discover

    return discover(
        planeops.importers,
        "IMPORTER",
        Importer,  # type: ignore[type-abstract]  # isinstance-only, see discover()
        key="kind",
    )
