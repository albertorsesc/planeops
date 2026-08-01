"""The report renderers: DRIFT.md (human pane) and DRIFT.json (machine pane).

The markdown pane is the one file a human routinely reads; these pin its actual
CONTENT (headers, counts, bullet shape, placeholders), not just that a file was
written somewhere.
"""

import json

from planeops.core.report import (
    DRIFT_SCHEMA_VERSION,
    DriftItem,
    DriftReport,
    drift_report_dict,
    render_drift,
    render_drift_json,
)


def _report():
    rep = DriftReport(host="h", ts="2026-07-31T00:00:00")
    rep.alerts = [
        DriftItem("launchd/zeta", "active", "expected present, not observed"),
        DriftItem(
            "launchd/alpha", "retired", "listed retired but still observed present"
        ),
    ]
    rep.report = [
        DriftItem(
            "manual/uv",
            "active",
            "attestation stale (>30d); run `plane observe --attest`",
        )
    ]
    rep.ungoverned = [
        DriftItem("pkg-brew/dep", "unregistered", "observed but not in the registry")
    ]
    return rep


def test_markdown_pane_carries_every_section_with_counts():
    md = render_drift(_report())
    assert md.startswith("# DRIFT")
    assert "Host: `h`" in md
    assert "2 alert(s), 1 report, 0 uncovered." in md
    for header in (
        "## Alerts (2)",
        "## Report (1)",
        "## Auto-folded (0)",
        "## Uncovered (0)",
        "## Ungoverned (1)",
        "## Re-auth pending (0)",
    ):
        assert header in md


def test_markdown_items_are_bulleted_and_sorted_by_entry_id():
    md = render_drift(_report())
    alpha = md.index(
        "- `launchd/alpha` (retired): listed retired but still observed present"
    )
    zeta = md.index("- `launchd/zeta` (active): expected present, not observed")
    assert alpha < zeta  # sorted, deterministic between runs
    assert "- `pkg-brew/dep` (unregistered): observed but not in the registry" in md


def test_markdown_empty_sections_show_a_placeholder():
    md = render_drift(_report())
    assert "_none_" in md  # an empty section reads as deliberately empty


def test_json_pane_mirrors_the_markdown_and_pins_the_schema():
    rep = _report()
    d = drift_report_dict(rep)
    assert d["schema_version"] == DRIFT_SCHEMA_VERSION
    assert d["alert_count"] == 2 and d["exit_code"] == 2
    assert d["summary"]["ungoverned"] == 1
    assert [i["entry_id"] for i in d["sections"]["alerts"]] == [
        "launchd/alpha",
        "launchd/zeta",
    ]
    assert json.loads(render_drift_json(rep)) == d  # the string form is the dict
