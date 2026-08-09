"""The footprint adapter: conventions scanned one level deep, merged per tool.

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
    def __init__(self, home: Path, name: str = "fake"):
        self._home = home
        self.name = name

    def hostname(self):
        return "h"

    def home(self):
        return self._home


def _ctx(tmp_path, inst=None, platform_name="fake"):
    return Ctx(
        platform=_Plat(tmp_path / "home", platform_name),
        host="h",
        now=datetime(2026, 8, 8),
        entries=(),
        repo_root=inst,
    )


XDG_ONLY = "footprint:\n  roots:\n    - {label: xdg-config, path: ~/.config}\n"


def _machine(tmp_path, roots_yaml=XDG_ONLY):
    home = tmp_path / "home"
    cfg = home / ".config"
    (cfg / "gh").mkdir(parents=True)
    (cfg / "uv").mkdir()
    (cfg / "starship.toml").write_text("format = ''\n")
    inst = tmp_path / "inst"
    inst.mkdir()
    (inst / ".planeops").write_text("")
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
        "footprints": [
            {"path": "~/.config/gh", "kind": "dir", "convention": "xdg-config"}
        ],
    }
    assert by_id["starship.toml"].facts["footprints"][0]["kind"] == "file"
    assert all(o.adapter == "footprint" for o in out)


def test_the_same_tool_across_roots_merges_into_one_observation(tmp_path):
    home, inst = _machine(
        tmp_path,
        "footprint:\n  roots:\n"
        "    - {label: xdg-config, path: ~/.config}\n"
        "    - {label: xdg-data, path: ~/.local/share}\n",
    )
    (home / ".local" / "share" / "gh").mkdir(parents=True)
    facts = _observe(tmp_path, inst)["gh"].facts
    assert [f["convention"] for f in facts["footprints"]] == ["xdg-config", "xdg-data"]
    assert [f["path"] for f in facts["footprints"]] == [
        "~/.config/gh",
        "~/.local/share/gh",
    ]


def test_the_merge_key_strips_leading_dots_and_case(tmp_path):
    # ~/.ollama and "Application Support/Ollama" are one tool, not three
    # spellings; the display names survive inside each footprint's path.
    home, inst = _machine(
        tmp_path,
        "footprint:\n  roots:\n"
        '    - {label: home-dot, path: "~", dot_only: true}\n'
        "    - {label: app-support, path: ~/Library/Application Support}\n",
    )
    (home / ".ollama").mkdir()
    (home / "Library" / "Application Support" / "Ollama").mkdir(parents=True)
    out = _observe(tmp_path, inst)
    assert "ollama" in out
    facts = out["ollama"].facts
    assert [f["path"] for f in facts["footprints"]] == [
        "~/.ollama",
        "~/Library/Application Support/Ollama",
    ]


def test_a_dot_only_root_skips_plain_children(tmp_path):
    home, inst = _machine(
        tmp_path,
        "footprint:\n  roots:\n"
        '    - {label: home-dot, path: "~", dot_only: true}\n'
        "    - {label: xdg-config, path: ~/.config}\n",
    )
    (home / "Documents").mkdir()
    (home / ".zshrc").write_text("")
    out = _observe(tmp_path, inst)
    assert "zshrc" in out and "documents" not in out
    assert out["zshrc"].facts["footprints"][0]["path"] == "~/.zshrc"


def test_a_child_that_is_another_root_is_not_a_tool(tmp_path):
    # `.config` is a convention we scan, not a tool that left a trace; the
    # same goes for `.local`, which merely holds the data root.
    home, inst = _machine(
        tmp_path,
        "footprint:\n  roots:\n"
        '    - {label: home-dot, path: "~", dot_only: true}\n'
        "    - {label: xdg-config, path: ~/.config}\n"
        "    - {label: xdg-data, path: ~/.local/share}\n",
    )
    (home / ".local" / "share" / "tirith").mkdir(parents=True)
    (home / ".zshrc").write_text("")
    out = _observe(tmp_path, inst)
    assert "config" not in out and "local" not in out
    assert "tirith" in out and "gh" in out and "zshrc" in out


def test_a_root_tagged_for_another_os_is_skipped(tmp_path):
    home, inst = _machine(
        tmp_path,
        "footprint:\n  roots:\n"
        "    - {label: xdg-config, path: ~/.config, os: linux}\n"
        "    - {label: app-support, path: ~/Library/Application Support, os: darwin}\n",
    )
    (home / "Library" / "Application Support" / "SomeApp").mkdir(parents=True)
    out = {
        o.native_id
        for o in ADAPTER.observe(_ctx(tmp_path, inst, platform_name="darwin"))
    }
    assert out == {"someapp"}  # the linux-tagged xdg root never scanned


def test_an_unknown_os_tag_raises(tmp_path):
    home, inst = _machine(
        tmp_path,
        "footprint:\n  roots:\n    - {label: x, path: ~/.config, os: darwn}\n",
    )
    with pytest.raises(ValueError, match="darwn"):
        ADAPTER.observe(_ctx(tmp_path, inst))


def test_a_symlinked_child_is_flagged_and_typed_by_its_target(tmp_path):
    home, inst = _machine(tmp_path)
    real = home / "dotfiles" / "wez"
    real.mkdir(parents=True)
    (home / ".config" / "wezterm").symlink_to(real)
    [fp] = _observe(tmp_path, inst)["wezterm"].facts["footprints"]
    assert fp["kind"] == "dir" and fp["symlink"] is True


def test_a_plain_child_carries_no_symlink_fact(tmp_path):
    home, inst = _machine(tmp_path)
    [fp] = _observe(tmp_path, inst)["gh"].facts["footprints"]
    assert "symlink" not in fp


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


def test_a_non_bool_dot_only_raises(tmp_path):
    home, inst = _machine(
        tmp_path,
        'footprint:\n  roots:\n    - {label: home-dot, path: "~", dot_only: sure}\n',
    )
    with pytest.raises(ValueError, match="dot_only"):
        ADAPTER.observe(_ctx(tmp_path, inst))


def test_a_bare_tilde_path_explains_the_yaml_null_trap(tmp_path):
    # `path: ~` is YAML null, the single likeliest way to write the home root
    # wrong; the refusal must say how to write it right.
    home, inst = _machine(
        tmp_path,
        "footprint:\n  roots:\n    - {label: home-dot, path: ~, dot_only: true}\n",
    )
    with pytest.raises(ValueError, match='written path: "~"'):
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
        assert facts["present"] is True
        assert facts["footprints"][0]["kind"] == "file"
    finally:
        os.chmod(locked, 0o600)


def test_an_all_dots_name_keeps_its_literal_key(tmp_path):
    # lstrip would empty it; the literal name is the only honest identity.
    home, inst = _machine(tmp_path)
    (home / ".config" / "...").mkdir()
    assert "..." in _observe(tmp_path, inst)


def test_the_adapter_is_discovered_and_observe_only(tmp_path):
    from planeops.core.discovery import discover_adapters

    adapter = discover_adapters().get("footprint")
    assert isinstance(adapter, FootprintAdapter)
    assert not hasattr(adapter, "plan") and not hasattr(adapter, "execute")
