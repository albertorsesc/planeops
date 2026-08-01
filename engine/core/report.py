"""Render a DriftReport two ways from one structure: `DRIFT.md` (the human pane)
and `DRIFT.json` (the machine pane).

Alerts lead; benign drift is compressed below. `DRIFT.md` is the only file a human
needs to check routinely; `DRIFT.json` is the same triage as stable JSON, so a
drift notification or the MCP surface reads structured data instead of scraping
markdown. Both draw from `_SECTIONS`, so a new section shows up in both at once.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DriftItem:
    entry_id: str
    lifecycle: str
    message: str


@dataclass(slots=True)
class DriftReport:
    """The pane model: triage (`engine.core.drift`) fills it, this module
    renders it. The types live with the renderers so the dependency points one
    way (drift -> report), instead of the old cycle hidden behind a
    function-local import."""

    host: str
    ts: str
    alerts: list[DriftItem] = field(default_factory=list)
    report: list[DriftItem] = field(default_factory=list)
    auto_folded: list[DriftItem] = field(default_factory=list)
    uncovered: list[DriftItem] = field(default_factory=list)
    ungoverned: list[DriftItem] = field(default_factory=list)
    reauth: list[DriftItem] = field(default_factory=list)

    @property
    def alert_count(self) -> int:
        return len(self.alerts)


_SECTIONS = [
    ("alerts", "Alerts", "lifecycle violations, missing required assets"),
    ("report", "Report", "drift worth a look"),
    ("auto_folded", "Auto-folded", "in-major version drift, folded"),
    ("uncovered", "Uncovered", "entries awaiting their adapter"),
    ("ungoverned", "Ungoverned", "observed on the machine, not in the registry"),
    ("reauth", "Re-auth pending", "interactive credentials to restore"),
]

# Bump when the JSON pane's shape changes, so a consumer can pin (mirrors the
# snapshot's schema_version).
DRIFT_SCHEMA_VERSION = 2


def _render_items(items: list[DriftItem]) -> str:
    if not items:
        return "_none_\n"
    lines = []
    for it in sorted(items, key=lambda i: i.entry_id):
        lines.append(f"- `{it.entry_id}` ({it.lifecycle}): {it.message}")
    return "\n".join(lines) + "\n"


def _item_dict(it: DriftItem) -> dict[str, str]:
    return {"entry_id": it.entry_id, "lifecycle": it.lifecycle, "message": it.message}


def drift_report_dict(report: DriftReport) -> dict[str, Any]:
    """The canonical machine-readable form of a DriftReport. Items are sorted by
    entry_id (same order the markdown uses) so the output is deterministic.
    `exit_code` mirrors the CLI: 2 when any alert exists, else 0, so a consumer
    reading the file gets the same verdict as the process exit."""
    sections: dict[str, list[dict[str, str]]] = {}
    for attr, _title, _blurb in _SECTIONS:
        items = sorted(getattr(report, attr), key=lambda it: it.entry_id)
        sections[attr] = [_item_dict(it) for it in items]
    return {
        "schema_version": DRIFT_SCHEMA_VERSION,
        "host": report.host,
        "ts": report.ts,
        "alert_count": report.alert_count,
        "exit_code": 2 if report.alert_count else 0,
        "summary": {attr: len(items) for attr, items in sections.items()},
        "sections": sections,
    }


def render_drift_json(report: DriftReport) -> str:
    return json.dumps(drift_report_dict(report), indent=2) + "\n"


def render_drift(report: DriftReport) -> str:
    out = [
        "# DRIFT",
        "",
        f"Host: `{report.host}`  ",
        f"Generated: {report.ts}",
        "",
        (
            f"{report.alert_count} alert(s), {len(report.report)} report, "
            f"{len(report.uncovered)} uncovered."
        ),
        "",
    ]
    for attr, title, blurb in _SECTIONS:
        items = getattr(report, attr)
        out.append(f"## {title} ({len(items)})")
        out.append(f"_{blurb}_")
        out.append("")
        out.append(_render_items(items))
    return "\n".join(out)
