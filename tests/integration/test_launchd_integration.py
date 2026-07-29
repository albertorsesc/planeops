"""Integration: the launchd adapter against the REAL launchctl (macOS).

The macOS parity to the sops/chezmoi integration tests. Scoped to a throwaway no-op
agent loaded from a TEMP plist path (never ~/Library/LaunchAgents), targeted only by
a unique test label, and booted out in teardown, so the machine's real services are
never touched and nothing is left loaded. No sudo (the user's own gui/<uid> domain).
Skipped off macOS, so it never runs (and never skips-as-pass silently) on Linux CI.
"""

import os
import plistlib
import shutil
import subprocess
import sys
import uuid
from datetime import datetime

import pytest

from engine.adapters.launchd import LaunchdAdapter
from engine.core.contracts import Ctx
from engine.core.schema import entry_from_dict

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("launchctl") is None,
    reason="requires macOS launchctl",
)

LABEL = f"com.planeops.integration-test.{os.getpid()}.{uuid.uuid4().hex[:8]}"


class _Platform:
    name = "darwin"

    def __init__(self, home):
        self._home = home

    def hostname(self) -> str:
        return "h"

    def home(self):
        return self._home


def _bootout() -> None:
    # Best-effort unload; errors (e.g. not loaded) are fine.
    subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True
    )


@pytest.fixture
def agents_dir(tmp_path):
    """A temp LaunchAgents dir holding one no-op test plist. Guarantees teardown:
    the label is booted out afterward no matter how the test ends."""
    d = tmp_path / "LaunchAgents"
    d.mkdir()
    with (d / f"{LABEL}.plist").open("wb") as fh:
        plistlib.dump(
            {
                "Label": LABEL,
                "ProgramArguments": ["/usr/bin/true"],  # no-op; never lingers
                "RunAtLoad": False,  # loaded/registered, but never actually runs
                "KeepAlive": False,
            },
            fh,
        )
    _bootout()  # clean slate in case a crashed prior run left it loaded
    try:
        yield d
    finally:
        _bootout()  # never leave the test agent loaded


def test_launchd_bootstrap_then_bootout_via_real_launchctl(agents_dir, tmp_path):
    ctx = Ctx(platform=_Platform(tmp_path), host="h", now=datetime(2026, 7, 28))
    adapter = LaunchdAdapter(agents_dir=agents_dir)  # temp dir, not ~/Library

    seen = {o.native_id: o for o in adapter.observe(ctx)}
    assert LABEL in seen and seen[LABEL].facts["loaded"] is False

    # active + unloaded -> bootstrap it (real launchctl)
    active = entry_from_dict(
        {"id": f"launchd/{LABEL}", "adapter": "launchd", "domain": "service",
         "lifecycle": "active", "intent": "i"}
    )  # fmt: skip
    [load] = adapter.plan(active, seen[LABEL], ctx)
    assert adapter.execute(load, ctx).ok

    seen = {o.native_id: o for o in adapter.observe(ctx)}
    assert seen[LABEL].facts["loaded"] is True  # launchctl actually loaded it

    # retired + loaded -> bootout it (real launchctl)
    retired = entry_from_dict(
        {"id": f"launchd/{LABEL}", "adapter": "launchd", "domain": "service",
         "lifecycle": "retired", "intent": "i"}
    )  # fmt: skip
    [unload] = adapter.plan(retired, seen[LABEL], ctx)
    assert adapter.execute(unload, ctx).ok

    seen = {o.native_id: o for o in adapter.observe(ctx)}
    assert seen[LABEL].facts["loaded"] is False  # launchctl actually unloaded it
