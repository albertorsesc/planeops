"""The footprint adapter, case one: one configured root, stat-only discovery.

Every test builds a fake home so nothing touches the real machine; the fake
platform confines the scan exactly as it does for the mcp adapter.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest

from planeops.adapters.footprint import ADAPTER, FootprintAdapter
from planeops.core.contracts import Ctx


class _Plat:
    name = "fake"

    def __init__(self, home: Path):
        self._home = home

    def hostname(self):
        return "h"

    def home(self):
        return self._home


def _ctx(tmp_path, inst=None):
    return Ctx(
        platform=_Plat(tmp_path / "home"),
        host="h",
        now=datetime(2026, 8, 8),
        entries=(),
        repo_root=inst,
    )


def _machine(tmp_path, roots_yaml=None):
    home = tmp_path / "home"
    cfg = home / ".config"
    (cfg / "gh").mkdir(parents=True)
    (cfg / "uv").mkdir()
    (cfg / "starship.toml").write_text("format = ''\n")
    inst = tmp_path / "inst"
    inst.mkdir()
    (inst / ".planeops").write_text("")
    if roots_yaml is None:
        roots_yaml = (
            "footprint:\n  roots:\n    - {label: xdg-config, path: ~/.config}\n"
        )
    (inst / "instance.yaml").write_text(roots_yaml)
    return home, inst


def _observe(tmp_path, inst):
    return {o.native_id: o for o in ADAPTER.observe(_ctx(tmp_path, inst))}


def test_observes_each_child_of_a_configured_root(tmp_path):
    home, inst = _machine(tmp_path)
    out = ADAPTER.observe(_ctx(tmp_path, inst))
    assert [o.native_id for o in out] == ["gh", "starship.toml", "uv"]  # sorted
    by_id = {o.native_id: o for o in out}
    assert by_id["gh"].facts == {
        "present": True,
        "kind": "dir",
        "path": "~/.config/gh",
        "convention": "xdg-config",
    }
    assert by_id["starship.toml"].facts["kind"] == "file"
    assert all(o.adapter == "footprint" for o in out)


def test_a_symlinked_child_is_flagged_and_typed_by_its_target(tmp_path):
    home, inst = _machine(tmp_path)
    real = home / "dotfiles" / "wez"
    real.mkdir(parents=True)
    (home / ".config" / "wezterm").symlink_to(real)
    facts = _observe(tmp_path, inst)["wezterm"].facts
    assert facts["kind"] == "dir" and facts["symlink"] is True


def test_a_plain_child_carries_no_symlink_fact(tmp_path):
    home, inst = _machine(tmp_path)
    assert "symlink" not in _observe(tmp_path, inst)["gh"].facts


def test_an_absent_root_is_quiet(tmp_path):
    home, inst = _machine(
        tmp_path,
        "footprint:\n  roots:\n    - {label: xdg-config, path: ~/.nonexistent}\n",
    )
    assert ADAPTER.observe(_ctx(tmp_path, inst)) == []


def test_no_section_means_no_scan(tmp_path):
    home, inst = _machine(tmp_path, "importer:\n  rules: []\n")
    assert ADAPTER.observe(_ctx(tmp_path, inst)) == []


def test_a_malformed_root_raises_instead_of_scanning_nothing(tmp_path):
    home, inst = _machine(
        tmp_path,
        "footprint:\n  roots:\n    - {label: xdg-config, paht: ~/.config}\n",
    )
    with pytest.raises(ValueError, match="paht"):
        ADAPTER.observe(_ctx(tmp_path, inst))


def test_discovery_is_stat_only_an_unreadable_file_is_still_observed(tmp_path):
    # Presence never requires reading: a credential file with owner-none mode
    # still contributes its name and shape.
    home, inst = _machine(tmp_path)
    locked = home / ".config" / "credentials.json"
    locked.write_text("{}")
    os.chmod(locked, 0o000)
    try:
        facts = _observe(tmp_path, inst)["credentials.json"].facts
        assert facts["present"] is True and facts["kind"] == "file"
    finally:
        os.chmod(locked, 0o600)


def test_the_adapter_is_discovered_and_observe_only(tmp_path):
    from planeops.core.discovery import discover_adapters

    adapter = discover_adapters().get("footprint")
    assert isinstance(adapter, FootprintAdapter)
    assert not hasattr(adapter, "plan") and not hasattr(adapter, "execute")
