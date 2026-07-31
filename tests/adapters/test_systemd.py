from datetime import datetime

from engine._run import RunResult
from engine.adapters.systemd import ADAPTER, SystemdAdapter
from engine.core.contracts import Change, Ctx, Observed, can_apply
from engine.core.schema import entry_from_dict


class Fake:
    """systemctl seam driven by a per-subcommand dispatch table (not an if-chain).
    is-enabled/is-active answer with a status WORD; list-units gates the session
    probe; enable/disable succeed unless the unit is in `fail`."""

    def __init__(self, *, session=True, enabled=(), active=(), static=(), fail=()):
        self.calls: list[list[str]] = []
        self.timeouts: list[float | None] = []
        self.session = session
        self.enabled = set(enabled)
        self.active = set(active)
        self.static = set(static)
        self.fail = set(fail)

    def _is_enabled(self, unit):
        if unit in self.static:
            return RunResult(0, "static")  # exit 0, but NOT enable-able
        return (
            RunResult(0, "enabled")
            if unit in self.enabled
            else RunResult(1, "disabled")
        )

    def _handlers(self):
        return {
            "list-units": lambda _u: RunResult(0 if self.session else 1),
            "is-enabled": self._is_enabled,
            "is-active": lambda u: (
                RunResult(0, "active") if u in self.active else RunResult(3, "inactive")
            ),
            "enable": lambda u: (
                RunResult(1, "", "boom") if u in self.fail else RunResult(0)
            ),
            "disable": lambda u: (
                RunResult(1, "", "boom") if u in self.fail else RunResult(0)
            ),
            "daemon-reload": lambda _u: RunResult(0),
        }

    def __call__(self, cmd, *, timeout=30):
        self.calls.append(cmd)
        self.timeouts.append(timeout)
        handler = self._handlers().get(cmd[2])
        return handler(cmd[-1]) if handler else RunResult(1, "", f"unexpected {cmd}")


def _units(tmp_path, *names):
    d = tmp_path / "user"
    d.mkdir()
    for n in names:
        (d / n).write_text("[Service]\nExecStart=/bin/true\n")
    return d


class _Plat:
    """Minimal Platform stub: plan/execute receive a real ctx, per the contract."""

    name = "fake"

    def hostname(self):
        return "h"

    def home(self):
        from pathlib import Path

        return Path("/home/fake")


def _ctx():
    return Ctx(platform=_Plat(), host="h", now=datetime(2026, 7, 28))


def _entry(unit, lifecycle="active"):
    return entry_from_dict(
        {"id": f"systemd/{unit}", "adapter": "systemd", "domain": "service",
         "lifecycle": lifecycle, "intent": "i"}
    )  # fmt: skip


def _obs(unit, enabled, active, path="/x"):
    return Observed(
        "systemd", unit, {"enabled": enabled, "active": active, "unit_path": path}
    )


# ---- observe -------------------------------------------------------------


def test_observe_reports_enabled_and_active(tmp_path):
    d = _units(tmp_path, "on.service", "off.service")
    fake = Fake(enabled={"on.service"}, active={"on.service"})
    out = {
        o.native_id: o for o in SystemdAdapter(run=fake, units_dir=d).observe(_ctx())
    }
    assert out["on.service"].facts == {
        "enabled": True,
        "active": True,
        "drifted": False,
        "always_on": True,
        "present": True,
        "unit_path": str(d / "on.service"),
    }
    assert out["off.service"].facts["enabled"] is False
    assert out["off.service"].facts["active"] is False
    assert out["on.service"].key == "systemd/on.service"


# ---- observe: dead-heartbeat drift (a unit meant to run but isn't) ----


def test_observe_flags_drift_when_an_installable_unit_is_disabled(tmp_path):
    # is-enabled reports 'disabled' (has [Install], currently off): the unit is meant to
    # be enabled and isn't, so it drifted. The dead-heartbeat signal for a scheduled
    # .timer that got disabled.
    d = _units(tmp_path, "sched.timer")
    out = SystemdAdapter(run=Fake(), units_dir=d).observe(_ctx())[0]  # not enabled
    assert out.facts["drifted"] is True


def test_observe_flags_drift_when_enabled_but_not_active(tmp_path):
    # enabled yet stopped (crashed / never started): still drift, mirrors plan's enable.
    d = _units(tmp_path, "svc.service")
    out = SystemdAdapter(run=Fake(enabled={"svc.service"}), units_dir=d).observe(_ctx())
    assert out[0].facts["drifted"] is True


def test_observe_no_drift_for_a_static_unit(tmp_path):
    # `static` (no [Install]) is not "disabled": a timer-driven oneshot .service stays
    # silent even while inactive between runs.
    d = _units(tmp_path, "oneshot.service")
    fake = Fake(static={"oneshot.service"})
    [obs] = SystemdAdapter(run=fake, units_dir=d).observe(_ctx())
    assert obs.facts["drifted"] is False


def test_observe_no_drift_when_enabled_and_active(tmp_path):
    d = _units(tmp_path, "sched.timer")
    fake = Fake(enabled={"sched.timer"}, active={"sched.timer"})
    [obs] = SystemdAdapter(run=fake, units_dir=d).observe(_ctx())
    assert obs.facts["drifted"] is False


def test_observe_degrades_without_a_user_session(tmp_path):
    d = _units(tmp_path, "x.service")
    assert SystemdAdapter(run=Fake(session=False), units_dir=d).observe(_ctx()) == []


def test_observe_empty_when_no_units_dir(tmp_path):
    assert SystemdAdapter(run=Fake(), units_dir=tmp_path / "nope").observe(_ctx()) == []


def test_observe_treats_a_static_unit_as_not_enabled(tmp_path):
    # is-enabled prints 'static' with exit 0; reading the word (not the exit code)
    # keeps a static unit from being reported enabled (regression: caught in CI).
    d = _units(tmp_path, "s.service")
    out = SystemdAdapter(run=Fake(static={"s.service"}), units_dir=d).observe(_ctx())[0]
    assert out.facts["enabled"] is False


def test_observe_skips_template_units(tmp_path):
    # a template (worker@.service) is not a runnable unit; instances are worker@X
    d = _units(tmp_path, "app.service", "worker@.service")
    out = {o.native_id for o in SystemdAdapter(run=Fake(), units_dir=d).observe(_ctx())}
    assert out == {"app.service"}


def test_observe_reports_timer_units_like_services(tmp_path):
    # A .timer is a unit too: observed exactly like a .service (no per-type branch),
    # so a scheduled reconcile timer is drift-tracked. Its template is skipped too.
    d = _units(tmp_path, "app.service", "sched.timer", "backup@.timer")
    fake = Fake(enabled={"sched.timer"}, active={"sched.timer"})
    out = {
        o.native_id: o for o in SystemdAdapter(run=fake, units_dir=d).observe(_ctx())
    }
    assert set(out) == {"app.service", "sched.timer"}  # backup@.timer template skipped
    assert out["sched.timer"].facts["enabled"] is True
    assert out["sched.timer"].facts["active"] is True


# ---- plan ----------------------------------------------------------------


def test_systemd_is_mutating():
    assert can_apply(ADAPTER)


def test_plan_enables_an_active_entry_that_is_off():
    [ch] = ADAPTER.plan(_entry("x.service"), _obs("x.service", False, False), _ctx())
    assert ch.kind == "configure"
    assert ch.action == {"op": "enable", "unit": "x.service", "unit_path": "/x"}


def test_plan_enables_a_scheduled_timer_that_is_off():
    # end-to-end: a .timer is planned/converged like any unit (enable --now the timer).
    [ch] = ADAPTER.plan(
        _entry("planeops-reconcile.timer"),
        _obs("planeops-reconcile.timer", False, False),
        _ctx(),
    )
    assert (
        ch.action["op"] == "enable" and ch.action["unit"] == "planeops-reconcile.timer"
    )


def test_plan_enables_when_active_but_not_enabled():
    # both axes must hold; enabled-but-inactive or active-but-disabled still converge
    [ch] = ADAPTER.plan(
        _entry("x.service"), _obs("x.service", enabled=True, active=False), _ctx()
    )
    assert ch.action["op"] == "enable"


def test_plan_noop_when_enabled_and_active():
    assert (
        ADAPTER.plan(_entry("x.service"), _obs("x.service", True, True), _ctx()) == []
    )


def test_plan_disables_a_retired_entry_that_is_on():
    [ch] = ADAPTER.plan(
        _entry("x.service", "retired"), _obs("x.service", True, True), _ctx()
    )
    assert ch.kind == "remove"
    assert ch.action == {
        "op": "disable",
        "unit": "x.service",
        "unit_path": "/x",
        "delete_unit": False,
    }


def test_plan_purge_deletes_the_unit_file():
    [ch] = ADAPTER.plan(
        _entry("x.service", "purge"), _obs("x.service", True, False), _ctx()
    )
    assert ch.action["delete_unit"] is True


def test_plan_retired_and_off_is_silent():
    assert (
        ADAPTER.plan(
            _entry("x.service", "retired"), _obs("x.service", False, False), _ctx()
        )
        == []
    )


def test_plan_none_obs_is_empty():
    assert ADAPTER.plan(_entry("x.service"), None, _ctx()) == []


# ---- execute -------------------------------------------------------------


def test_execute_enable_reloads_then_enables():
    fake = Fake()
    ch = Change("systemd/x.service", "configure", "d",
                {"op": "enable", "unit": "x.service", "unit_path": "/x"})  # fmt: skip
    assert SystemdAdapter(run=fake).execute(ch, _ctx()).ok
    assert fake.calls == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "x.service"],
    ]


def test_execute_disable():
    fake = Fake()
    ch = Change("systemd/x.service", "remove", "d",
                {"op": "disable", "unit": "x.service", "unit_path": "/x", "delete_unit": False})  # fmt: skip
    assert SystemdAdapter(run=fake).execute(ch, _ctx()).ok
    assert ["systemctl", "--user", "disable", "--now", "x.service"] in fake.calls


def test_execute_purge_unlinks_unit_file(tmp_path):
    unit = tmp_path / "x.service"
    unit.write_text("[Service]\n")
    fake = Fake()
    ch = Change("systemd/x.service", "remove", "d",
                {"op": "disable", "unit": "x.service", "unit_path": str(unit), "delete_unit": True})  # fmt: skip
    res = SystemdAdapter(run=fake).execute(ch, _ctx())
    assert res.ok and not unit.exists()
    assert ["systemctl", "--user", "daemon-reload"] in fake.calls


def test_execute_failure_and_unknown_op():
    fail = Fake(fail={"x.service"})
    bad = Change("systemd/x.service", "configure", "d",
                 {"op": "enable", "unit": "x.service", "unit_path": "/x"})  # fmt: skip
    assert not SystemdAdapter(run=fail).execute(bad, _ctx()).ok
    unknown = Change("systemd/x", "configure", "d", {"op": "bogus", "unit": "x"})
    assert not SystemdAdapter(run=Fake()).execute(unknown, _ctx()).ok


def test_observe_marks_always_on_for_enabled_units(tmp_path):
    # enabled = starts at login; feeds drift's ungoverned always-on alert.
    d = _units(tmp_path, "on.service", "off.service")
    fake = Fake(enabled={"on.service"}, active={"on.service"})
    out = {
        o.native_id: o for o in SystemdAdapter(run=fake, units_dir=d).observe(_ctx())
    }
    assert out["on.service"].facts["always_on"] is True
    assert out["off.service"].facts["always_on"] is False


def test_observe_present_means_enabled_or_active(tmp_path):
    # Semantic presence for a unit is "will run or is running", not "file exists".
    d = _units(tmp_path, "on.service", "running.service", "off.service")
    fake = Fake(enabled={"on.service"}, active={"running.service"})
    out = {
        o.native_id: o for o in SystemdAdapter(run=fake, units_dir=d).observe(_ctx())
    }
    assert out["on.service"].facts["present"] is True  # enabled, not started
    assert out["running.service"].facts["present"] is True  # active only
    assert out["off.service"].facts["present"] is False
