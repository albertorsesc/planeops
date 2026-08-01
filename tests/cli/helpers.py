"""Shared builders for the per-verb CLI tests: canned drift reports, stored
status payloads, and MCP views, so each verb file stubs the engine the same way."""

from planeops.core.report import DriftItem, DriftReport


def _report(alerts=0):
    rep = DriftReport(host="h", ts="2026-07-28T00:00:00")
    rep.alerts = [DriftItem(f"manual/a{i}", "active", "expected present, not observed")
                  for i in range(alerts)]  # fmt: skip
    return rep


def _status(alert_count, report=0, uncovered=0):
    return {
        "alert_count": alert_count,
        "ts": "2026-07-29T00:00:00",
        "summary": {"report": report, "uncovered": uncovered},
        "sections": {},
    }


def _mcp_view():
    return {
        "host": "h",
        "ts": "2026-07-29T00:00:00",
        "servers": [
            {
                "name": "context7",
                "id": "mcp/context7",
                "clients": ["claude-code"],
                "governed": True,
            },
            {
                "name": "tolaria",
                "id": "mcp/tolaria",
                "clients": ["cursor"],
                "governed": False,
            },
        ],
        "single_client": ["context7", "tolaria"],
        "ungoverned": ["tolaria"],
        "name_drift": [],
    }
