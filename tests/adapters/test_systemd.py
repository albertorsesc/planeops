from datetime import datetime

from engine._run import RunResult
from engine.adapters.systemd import ADAPTER, SystemdAdapter
from engine.core.contracts import Change, Ctx, Observed, can_apply
from engine.core.schema import entry_from_dict


class Fake:
    """systemctl seam: is-enabled/is-active answer by exit code; list-units gates
    the session probe; enable/disable succeed unless the unit is in `fail`."""

    def __init__(self, *, session=True, enabled=(), active=(), fail=()):
        self.calls: list[list[str]] = []
        self.session = session
        self.enabled = set(enabled)
        self.active = set(active)
        self.fail = set(fail)

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd == ["systemctl", "--user", "list-units", "--no-legend"]:
            return RunResult(0 if self.session else 1)
        if len(cmd) == 5 and cmd[2] == "is-enabled":
            return RunResult(0 if cmd[4] in self.enabled else 1)
        if len(cmd) == 5 and cmd[2] == "is-active":
            return RunResult(0 if cmd[4] in self.active else 3)
        if cmd[2] in ("enable", "disable"):
            return RunResult(1, "", "boom") if cmd[-1] in self.fail else RunResult(0)
        if cmd[2] == "daemon-reload":
            return RunResult(0)
        return RunResult(1, "", "unexpected")


def _units(tmp_path, *names):
    d = tmp_path / "user"
    d.mkdir()
    for n in names:
        (d / n).write_text("[Service]\nExecStart=/bin/true\n")
    return d


def _ctx():
    return Ctx(platform=None, host="h", now=datetime(2026, 7, 28))


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
        "unit_path": str(d / "on.service"),
    }
    assert out["off.service"].facts["enabled"] is False
    assert out["off.service"].facts["active"] is False
    assert out["on.service"].key == "systemd/on.service"


def test_observe_degrades_without_a_user_session(tmp_path):
    d = _units(tmp_path, "x.service")
    assert SystemdAdapter(run=Fake(session=False), units_dir=d).observe(_ctx()) == []


def test_observe_empty_when_no_units_dir(tmp_path):
    assert SystemdAdapter(run=Fake(), units_dir=tmp_path / "nope").observe(_ctx()) == []


# ---- plan ----------------------------------------------------------------


def test_systemd_is_mutating():
    assert can_apply(ADAPTER)


def test_plan_enables_an_active_entry_that_is_off():
    [ch] = ADAPTER.plan(_entry("x.service"), _obs("x.service", False, False))
    assert ch.kind == "configure"
    assert ch.action == {"op": "enable", "unit": "x.service", "unit_path": "/x"}


def test_plan_enables_when_active_but_not_enabled():
    # both axes must hold; enabled-but-inactive or active-but-disabled still converge
    [ch] = ADAPTER.plan(
        _entry("x.service"), _obs("x.service", enabled=True, active=False)
    )
    assert ch.action["op"] == "enable"


def test_plan_noop_when_enabled_and_active():
    assert ADAPTER.plan(_entry("x.service"), _obs("x.service", True, True)) == []


def test_plan_disables_a_retired_entry_that_is_on():
    [ch] = ADAPTER.plan(_entry("x.service", "retired"), _obs("x.service", True, True))
    assert ch.kind == "remove"
    assert ch.action == {
        "op": "disable",
        "unit": "x.service",
        "unit_path": "/x",
        "delete_unit": False,
    }


def test_plan_purge_deletes_the_unit_file():
    [ch] = ADAPTER.plan(_entry("x.service", "purge"), _obs("x.service", True, False))
    assert ch.action["delete_unit"] is True


def test_plan_retired_and_off_is_silent():
    assert (
        ADAPTER.plan(_entry("x.service", "retired"), _obs("x.service", False, False))
        == []
    )


def test_plan_none_obs_is_empty():
    assert ADAPTER.plan(_entry("x.service"), None) == []


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
