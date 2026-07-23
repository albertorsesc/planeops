"""Render a DriftReport as `DRIFT.md`: the single visibility pane.

Alerts lead; benign drift is compressed below. This is the only file a human
needs to check routinely.
"""

from __future__ import annotations

from engine.core.drift import DriftItem, DriftReport

_SECTIONS = [
    ("alerts", "Alerts", "lifecycle violations, missing required assets"),
    ("report", "Report", "drift worth a look"),
    ("auto_folded", "Auto-folded", "in-major version drift, folded"),
    ("uncovered", "Uncovered", "entries awaiting their adapter"),
    ("reauth", "Re-auth pending", "interactive credentials to restore"),
]


def _render_items(items: list[DriftItem]) -> str:
    if not items:
        return "_none_\n"
    lines = []
    for it in sorted(items, key=lambda i: i.entry_id):
        lines.append(f"- `{it.entry_id}` ({it.lifecycle}): {it.message}")
    return "\n".join(lines) + "\n"


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
