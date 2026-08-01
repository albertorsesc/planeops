"""The schedulers package seam: backend discovery and per-platform selection.
Backend generation lives in test_launchd.py / test_systemd.py; the `plane
schedule` CLI wiring lives in tests/test_cli.py."""

from engine.schedulers import discover_schedulers


def test_discovery_finds_both_backends_selected_by_platform():
    by_name = {s.name: s for s in discover_schedulers()}
    assert "launchd" in by_name and "systemd" in by_name
    assert "darwin" in by_name["launchd"].sys_platforms
    assert "linux" in by_name["systemd"].sys_platforms
