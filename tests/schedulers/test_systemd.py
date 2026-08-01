"""systemd scheduler backend: pure generation of the reconcile timer + oneshot
service pair, the governed entry, and its refusal of unsafe values."""

import pytest

from engine.schedulers.systemd import SCHEDULER as SYSTEMD


def test_pairs_timer_and_service_and_unmanages_the_service(tmp_path):
    job = SYSTEMD.build(
        tmp_path, plane="/x/plane", path_env="/p",
        interval=21600, login=True, off=False,
    )  # fmt: skip
    assert sorted(p.name for p in job.files) == [
        "planeops-reconcile.service",
        "planeops-reconcile.timer",
    ]
    timer = next(c for p, c in job.files.items() if p.name.endswith(".timer"))
    assert "OnUnitActiveSec=21600s" in timer and "OnBootSec" in timer
    svc = next(c for p, c in job.files.items() if p.name.endswith(".service"))
    assert "ExecStart=/x/plane reconcile" in svc and "Environment=PATH=/p" in svc
    assert job.entries[0]["id"] == "systemd/planeops-reconcile.timer"
    assert job.entries[0]["tolerance"] == "alert"  # dead-heartbeat escalates
    # the timer-driven oneshot is bundled but not governed on its own
    assert job.globs == [{"glob": "systemd/planeops-reconcile.service"}]


def test_no_login_timer_still_gets_a_first_fire(tmp_path):
    # OnUnitActiveSec alone never fires: it is relative to the SERVICE's last
    # activation, which never happens on a fresh enable (live-verified: NEXT
    # stayed empty). OnActiveSec is relative to the TIMER's activation, so
    # enabling schedules the first run; OnUnitActiveSec then keeps the cadence.
    job = SYSTEMD.build(
        tmp_path, plane="p", path_env="", interval=21600, login=False, off=False
    )
    timer = next(c for p, c in job.files.items() if p.name.endswith(".timer"))
    assert "OnActiveSec=21600s" in timer
    assert "OnUnitActiveSec=21600s" in timer
    assert "OnBootSec" not in timer  # --no-login: no boot/login trigger
    # Persistent= only affects OnCalendar timers; on monotonic ones it is a
    # silent no-op, so shipping it would just be a false promise.
    assert "Persistent" not in timer


def test_build_refuses_directive_injection_via_values(tmp_path):
    # The unit file is plain-text concatenation; a newline inside PATH or the
    # plane path would land as a new directive line. Refuse loudly.
    with pytest.raises(ValueError, match="newline"):
        SYSTEMD.build(
            tmp_path, plane="/bin/plane", path_env="/usr/bin\nExecStartPre=/evil",
            interval=60, login=True, off=False,
        )  # fmt: skip
    with pytest.raises(ValueError, match="newline"):
        SYSTEMD.build(
            tmp_path, plane="/bin/pl\nane", path_env="/usr/bin",
            interval=60, login=True, off=False,
        )  # fmt: skip
