"""Integration: the systemd adapter against the REAL systemctl --user (Linux).

The Linux parity to the launchd integration test. Enables then disables a throwaway
no-op user unit through the real systemctl and asserts observe reflects the
enabled/active state. Uses a unique per-run unit name under ~/.config/systemd/user
and disables + removes it in teardown, so nothing is left enabled/running.

Skipped unless a real `systemd --user` session is reachable, so it does NOT run on
macOS (no systemd) or in a session-less environment, only where systemctl --user
actually works (a systemd Linux; CI sets that up). No sudo.
"""

import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from engine.adapters.systemd import SystemdAdapter
from engine.core.contracts import Ctx
from engine.core.schema import entry_from_dict


def _user_systemd_ok() -> bool:
    if sys.platform == "darwin" or shutil.which("systemctl") is None:
        return False
    try:
        r = subprocess.run(
            ["systemctl", "--user", "list-units", "--no-legend"], capture_output=True
        )
        return r.returncode == 0
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _user_systemd_ok(), reason="requires a working systemd --user session"
)

UNIT = f"planeops-integration-test-{os.getpid()}-{uuid.uuid4().hex[:8]}.service"
_USER_DIR = Path.home() / ".config" / "systemd" / "user"


class _Platform:
    name = "linux"

    def __init__(self, home):
        self._home = home

    def hostname(self) -> str:
        return "h"

    def home(self):
        return self._home


def _cleanup() -> None:
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", UNIT], capture_output=True
    )
    (_USER_DIR / UNIT).unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)


@pytest.fixture
def unit_file():
    _USER_DIR.mkdir(parents=True, exist_ok=True)
    try:
        # Inside the try so cleanup runs even if setup (write/daemon-reload) fails.
        (_USER_DIR / UNIT).write_text(
            "[Unit]\nDescription=planeops test\n"
            "[Service]\nExecStart=/bin/sleep 3600\n"
            "[Install]\nWantedBy=default.target\n"  # enable-able (not a `static` unit)
        )
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        yield
    finally:
        _cleanup()  # never leave the test unit enabled/running or on disk


def test_enable_then_disable_via_real_systemctl(unit_file):
    ctx = Ctx(platform=_Platform(Path.home()), host="h", now=datetime(2026, 7, 28))
    adapter = SystemdAdapter()  # real systemctl, default ~/.config/systemd/user

    seen = {o.native_id: o for o in adapter.observe(ctx)}
    assert UNIT in seen
    assert seen[UNIT].facts["enabled"] is False
    assert seen[UNIT].facts["active"] is False

    active = entry_from_dict(
        {"id": f"systemd/{UNIT}", "adapter": "systemd", "domain": "service",
         "lifecycle": "active", "intent": "i"}
    )  # fmt: skip
    [enable] = adapter.plan(active, seen[UNIT], ctx)
    assert adapter.execute(enable, ctx).ok

    seen = {o.native_id: o for o in adapter.observe(ctx)}
    assert seen[UNIT].facts["enabled"] is True  # real systemctl enabled it
    assert seen[UNIT].facts["active"] is True  # real systemctl started it

    retired = entry_from_dict(
        {"id": f"systemd/{UNIT}", "adapter": "systemd", "domain": "service",
         "lifecycle": "retired", "intent": "i"}
    )  # fmt: skip
    [disable] = adapter.plan(retired, seen[UNIT], ctx)
    assert adapter.execute(disable, ctx).ok

    seen = {o.native_id: o for o in adapter.observe(ctx)}
    assert seen[UNIT].facts["enabled"] is False  # real systemctl disabled it
    assert seen[UNIT].facts["active"] is False  # real systemctl stopped it


TIMER = f"planeops-integration-timer-{os.getpid()}-{uuid.uuid4().hex[:8]}.timer"
TIMER_SVC = TIMER.replace(".timer", ".service")


def _cleanup_timer() -> None:
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", TIMER], capture_output=True
    )
    (_USER_DIR / TIMER).unlink(missing_ok=True)
    (_USER_DIR / TIMER_SVC).unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)


@pytest.fixture
def timer_files():
    _USER_DIR.mkdir(parents=True, exist_ok=True)
    try:
        # a timer needs the service it triggers to exist
        (_USER_DIR / TIMER_SVC).write_text(
            "[Unit]\nDescription=planeops test svc\n"
            "[Service]\nType=oneshot\nExecStart=/bin/true\n"
        )
        (_USER_DIR / TIMER).write_text(
            "[Unit]\nDescription=planeops test timer\n"
            "[Timer]\nOnActiveSec=1h\n"
            "[Install]\nWantedBy=timers.target\n"  # enable-able
        )
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        yield
    finally:
        _cleanup_timer()


def test_observe_and_govern_a_real_timer(timer_files):
    # The Linux parity to a scheduled launchd plist: the adapter observes and converges
    # a real `.timer` via systemctl, so `plane schedule`'s reconcile timer is governed.
    ctx = Ctx(platform=_Platform(Path.home()), host="h", now=datetime(2026, 7, 28))
    adapter = SystemdAdapter()

    seen = {o.native_id: o for o in adapter.observe(ctx)}
    assert TIMER in seen  # .timer units are observed, not just .service
    assert seen[TIMER].facts["enabled"] is False
    assert seen[TIMER].facts["active"] is False

    active = entry_from_dict(
        {"id": f"systemd/{TIMER}", "adapter": "systemd", "domain": "service",
         "lifecycle": "active", "intent": "i"}
    )  # fmt: skip
    [enable] = adapter.plan(active, seen[TIMER], ctx)
    assert adapter.execute(enable, ctx).ok

    seen = {o.native_id: o for o in adapter.observe(ctx)}
    assert seen[TIMER].facts["enabled"] is True  # real systemctl enabled the timer
    assert seen[TIMER].facts["active"] is True  # real systemctl started the timer
