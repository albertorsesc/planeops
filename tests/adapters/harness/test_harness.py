"""The harness adapter: code plugged into an AI harness, hooks first.

A hook runs code unprompted on every tool call, so it is the part of a
harness a control plane cannot afford to be blind to.

Generic labels, paths, and schema throughout: the adapter names no real tool,
and every harness under test here is invented for the test. What a specific
tool's settings file looks like is that harness leaf's business, tested under
`harnesses/`. Every test builds a fake home, so nothing reads a real machine.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from planeops.adapters.harness import ADAPTER, HarnessAdapter, KnownHarness
from planeops.core.contracts import Ctx


class _Plat:
    def __init__(self, home: Path, name: str = "fake"):
        self._home = home
        self.name = name

    def hostname(self):
        return "h"

    def home(self):
        return self._home

    def os_component(self, name):
        return None


def _ctx(tmp_path, inst=None):
    return Ctx(
        platform=_Plat(tmp_path / "home"),
        host="h",
        now=datetime(2026, 8, 10),
        entries=(),
        repo_root=inst,
    )


def _read_hooks(data: dict) -> list[tuple[str, str]]:
    """The invented harness's schema: `{"on": {<event>: [<command>, ...]}}`.
    Deliberately unlike any real tool's, so nothing in the adapter can be
    tuned to one vendor's shape."""
    out = []
    for event, commands in (data.get("on") or {}).items():
        for command in commands:
            out.append((event, command))
    return out


HARNESS = KnownHarness(label="probe", config="config.json", hooks=_read_hooks)
ONE = "harness:\n  profiles:\n    - {label: probe, path: ~/.probe}\n"


def _machine(tmp_path, on=None, yaml=ONE, scripts=("checks/alpha.sh",)):
    home = tmp_path / "home"
    prof = home / ".probe"
    prof.mkdir(parents=True)
    for rel in scripts:
        p = prof / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/bin/sh\n")
    if on is None:
        on = {"before-tool": [str(prof / "checks/alpha.sh")]}
    (prof / "config.json").write_text(json.dumps({"on": on}))
    inst = tmp_path / "inst"
    inst.mkdir()
    (inst / ".planeops").write_text("")
    (inst / "instance.yaml").write_text(yaml)
    return home, inst


def _adapter():
    return HarnessAdapter(harnesses={"probe": HARNESS})


def _observe(tmp_path, inst):
    return {o.native_id: o for o in _adapter().observe(_ctx(tmp_path, inst))}


# ---- identity and facts ----------------------------------------------------


def test_a_hook_is_observed_by_kind_event_and_script(tmp_path):
    home, inst = _machine(tmp_path)
    out = _observe(tmp_path, inst)
    assert list(out) == ["hook/before-tool/alpha"]
    facts = out["hook/before-tool/alpha"].facts
    assert facts["kind"] == "hook"
    assert facts["event"] == "before-tool"
    assert facts["present"] is True
    assert facts["always_on"] is True  # it runs code without being asked
    assert facts["runs"] == "~/.probe/checks/alpha.sh"
    assert facts["harness"] == "probe"  # which tool
    assert facts["profiles"] == ["~/.probe"]  # which of its config dirs


def test_the_command_string_is_never_recorded(tmp_path):
    # A command is a shell string that can carry a token; the script path is
    # the identity, so the raw command never reaches the snapshot.
    home, inst = _machine(
        tmp_path,
        {"before-tool": [f"{tmp_path}/home/.probe/checks/alpha.sh --key=sk-SENTINEL"]},
    )
    blob = json.dumps([o.facts for o in _adapter().observe(_ctx(tmp_path, inst))])
    assert "SENTINEL" not in blob


def test_a_hook_whose_script_is_gone_is_not_present(tmp_path):
    # It is wired but cannot run: the same violation as any active asset that
    # is not there, and the triage turns present False into an alert.
    home, inst = _machine(tmp_path, {"before-tool": ["/nowhere/vanished.sh"]})
    [obs] = _adapter().observe(_ctx(tmp_path, inst))
    assert obs.facts["present"] is False
    assert obs.facts["runs"] == "/nowhere/vanished.sh"


def test_a_script_run_through_an_interpreter_is_present(tmp_path):
    # A command may name a runtime and pass the script as an argument, and
    # such a file is deliberately not executable. Checking the executable bit
    # instead of resolvability raises false alerts on ordinary setups.
    home, inst = _machine(
        tmp_path,
        {"before-tool": [f'node "{tmp_path}/home/.probe/plug/beta.cjs"']},
        scripts=("plug/beta.cjs",),
    )
    [obs] = _adapter().observe(_ctx(tmp_path, inst))
    assert obs.facts["present"] is True
    assert obs.native_id == "hook/before-tool/beta"


def test_an_inline_command_is_present_and_names_no_script(tmp_path):
    home, inst = _machine(tmp_path, {"before-tool": ["echo hello"]})
    [obs] = _adapter().observe(_ctx(tmp_path, inst))
    assert obs.facts["present"] is True
    assert "runs" not in obs.facts
    assert obs.native_id.startswith("hook/before-tool/")


# ---- profiles --------------------------------------------------------------


def test_the_same_hook_in_two_profiles_is_one_observation(tmp_path):
    # One machine commonly runs several profiles of the SAME harness, so the
    # profiles fact must name the config dirs, not repeat the tool's label.
    home, inst = _machine(
        tmp_path,
        yaml=(
            "harness:\n  profiles:\n"
            "    - {label: probe, path: ~/.probe}\n"
            "    - {label: probe, path: ~/.probe-second}\n"
        ),
    )
    second = home / ".probe-second"
    second.mkdir()
    (second / "config.json").write_text((home / ".probe" / "config.json").read_text())
    out = _observe(tmp_path, inst)
    assert len(out) == 1
    facts = out["hook/before-tool/alpha"].facts
    assert facts["harness"] == "probe"
    assert facts["profiles"] == ["~/.probe", "~/.probe-second"]


def test_a_profile_with_no_config_file_is_quiet(tmp_path):
    home, inst = _machine(
        tmp_path,
        yaml=(
            "harness:\n  profiles:\n"
            "    - {label: probe, path: ~/.probe}\n"
            "    - {label: probe, path: ~/.absent}\n"
        ),
    )
    assert len(_observe(tmp_path, inst)) == 1  # the absent one simply is not here


# ---- collisions ------------------------------------------------------------


def test_two_hooks_sharing_an_event_and_a_script_name_stay_distinct(tmp_path):
    base = f"{tmp_path}/home/.probe"
    home, inst = _machine(
        tmp_path,
        {"before-tool": [f"{base}/one/same.sh", f"{base}/two/same.sh"]},
        scripts=("one/same.sh", "two/same.sh"),
    )
    out = _observe(tmp_path, inst)
    assert len(out) == 2, sorted(out)  # neither silently swallows the other


def test_the_same_script_on_two_events_is_two_hooks(tmp_path):
    cmd = f"{tmp_path}/home/.probe/checks/alpha.sh"
    home, inst = _machine(tmp_path, {"before-tool": [cmd], "after-run": [cmd]})
    assert set(_observe(tmp_path, inst)) == {
        "hook/before-tool/alpha",
        "hook/after-run/alpha",
    }


# ---- configuration ---------------------------------------------------------


def test_no_section_means_no_scan(tmp_path):
    home, inst = _machine(tmp_path, yaml="importer:\n  rules: []\n")
    assert _adapter().observe(_ctx(tmp_path, inst)) == []


def test_a_malformed_profile_raises_instead_of_scanning_nothing(tmp_path):
    home, inst = _machine(
        tmp_path,
        yaml="harness:\n  profiles:\n    - {label: probe, paht: ~/.probe}\n",
    )
    with pytest.raises(ValueError, match="paht"):
        _adapter().observe(_ctx(tmp_path, inst))


def test_a_profile_naming_an_unknown_harness_raises(tmp_path):
    # Without a known harness the adapter cannot read that tool's layout, so
    # the profile would be a silent coverage hole unless it refuses.
    home, inst = _machine(
        tmp_path,
        yaml="harness:\n  profiles:\n    - {label: nobody, path: ~/.probe}\n",
    )
    with pytest.raises(ValueError, match="nobody"):
        _adapter().observe(_ctx(tmp_path, inst))


def test_profiles_that_are_not_a_list_raise(tmp_path):
    home, inst = _machine(
        tmp_path,
        yaml="harness:\n  profiles:\n    label: probe\n    path: ~/.probe\n",
    )
    with pytest.raises(ValueError, match="list of mappings"):
        _adapter().observe(_ctx(tmp_path, inst))


def test_an_unreadable_config_refuses_loudly(tmp_path):
    home, inst = _machine(tmp_path)
    (home / ".probe" / "config.json").write_text("{not json")
    with pytest.raises(ValueError, match="config.json"):
        _adapter().observe(_ctx(tmp_path, inst))


def test_a_config_declaring_no_hooks_is_quiet(tmp_path):
    home, inst = _machine(tmp_path, on={})
    assert _adapter().observe(_ctx(tmp_path, inst)) == []


# ---- contract --------------------------------------------------------------


def test_the_adapter_is_discovered_and_observe_only():
    from planeops.core.discovery import discover_adapters

    adapter = discover_adapters().get("harness")
    assert isinstance(adapter, HarnessAdapter)
    assert not hasattr(adapter, "plan") and not hasattr(adapter, "execute")
    assert ADAPTER.name == "harness"


def test_the_adapter_names_no_real_tool():
    # Vendor knowledge belongs in a harness leaf, never in the adapter.
    src = Path("planeops/adapters/harness/__init__.py").read_text()
    for vendor in ("claude", "cursor", "copilot", "codex", "settings.json"):
        assert vendor not in src.lower()
