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
from planeops.core.schema import entry_from_dict


class _Plat:
    def __init__(self, home: Path, name: str = "fake"):
        self._home = home
        self.name = name

    def hostname(self):
        return "h"

    def home(self):
        return self._home


def _ctx(tmp_path, inst=None, platform_name="fake", entries=()):
    return Ctx(
        platform=_Plat(tmp_path / "home", platform_name),
        host="h",
        now=datetime(2026, 8, 8),
        entries=tuple(entries),
        repo_root=inst,
    )


def _entry(eid, adapter):
    domain = {"footprint": "footprint"}.get(adapter, "package")
    return entry_from_dict(
        {"id": eid, "adapter": adapter, "domain": domain,
         "lifecycle": "active", "intent": "i"}
    )  # fmt: skip


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


def test_a_non_bool_ignore_defaults_raises(tmp_path):
    home, inst = _machine(
        tmp_path,
        "footprint:\n  ignore_defaults: sure\n  roots:\n"
        "    - {label: xdg-config, path: ~/.config}\n",
    )
    with pytest.raises(ValueError, match="ignore_defaults"):
        ADAPTER.observe(_ctx(tmp_path, inst))


def test_a_non_mapping_root_raises(tmp_path):
    home, inst = _machine(tmp_path, "footprint:\n  roots:\n    - just-a-string\n")
    with pytest.raises(ValueError, match="mapping"):
        ADAPTER.observe(_ctx(tmp_path, inst))


def test_an_empty_label_raises(tmp_path):
    home, inst = _machine(
        tmp_path,
        'footprint:\n  roots:\n    - {label: "", path: ~/.config}\n',
    )
    with pytest.raises(ValueError, match="label"):
        ADAPTER.observe(_ctx(tmp_path, inst))


def test_a_non_string_path_raises(tmp_path):
    home, inst = _machine(
        tmp_path,
        "footprint:\n  roots:\n    - {label: x, path: 3}\n",
    )
    with pytest.raises(ValueError, match="path must be"):
        ADAPTER.observe(_ctx(tmp_path, inst))


def test_a_root_outside_home_displays_its_absolute_path(tmp_path):
    outside = tmp_path / "opt" / "shared-tools"
    (outside / "modelpack").mkdir(parents=True)
    home, inst = _machine(
        tmp_path,
        f"footprint:\n  roots:\n    - {{label: shared, path: {outside}}}\n",
    )
    [fp] = _observe(tmp_path, inst)["modelpack"].facts["footprints"]
    assert fp["path"] == str(outside / "modelpack")  # absolute, no ~ to relate


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


def test_a_unicode_name_folds_case_like_any_other(tmp_path):
    home, inst = _machine(tmp_path)
    (home / ".config" / "陽Tool").mkdir()
    assert "陽tool" in _observe(tmp_path, inst)


def test_an_all_dots_name_keeps_its_literal_key(tmp_path):
    # lstrip would empty it; the literal name is the only honest identity.
    home, inst = _machine(tmp_path)
    (home / ".config" / "...").mkdir()
    assert "..." in _observe(tmp_path, inst)


def test_default_noise_names_are_never_tools(tmp_path):
    # OS artifacts, shell/editor state, backup copies, and the cache dir are
    # debris, not tools; they must not become 11 open questions.
    home, inst = _machine(
        tmp_path,
        "footprint:\n  roots:\n"
        '    - {label: home-dot, path: "~", dot_only: true}\n'
        "    - {label: xdg-config, path: ~/.config}\n",
    )
    for name in (".DS_Store", ".Trash", ".cache", ".viminfo", ".zsh_history"):
        p = home / name
        p.mkdir() if name in (".Trash", ".cache") else p.write_text("")
    (home / ".config" / "settings.json.bak").write_text("")
    out = _observe(tmp_path, inst)
    for absent in (
        "ds_store",
        "trash",
        "cache",
        "viminfo",
        "zsh_history",
        "settings.json.bak",
    ):
        assert absent not in out, absent  # fmt: skip
    assert "gh" in out  # real tools unaffected


def test_the_ignore_list_extends_the_defaults(tmp_path):
    home, inst = _machine(
        tmp_path,
        "footprint:\n"
        "  ignore: [gh]\n"
        "  roots:\n    - {label: xdg-config, path: ~/.config}\n",
    )
    out = _observe(tmp_path, inst)
    assert "gh" not in out and "uv" in out


def test_ignore_defaults_false_restores_the_debris(tmp_path):
    home, inst = _machine(
        tmp_path,
        "footprint:\n"
        "  ignore_defaults: false\n"
        "  roots:\n    - {label: xdg-config, path: ~/.config}\n",
    )
    (home / ".config" / ".DS_Store").write_text("")
    assert "ds_store" in _observe(tmp_path, inst)


def test_ignore_matches_the_literal_name_case_sensitively(tmp_path):
    # fnmatchcase on both OSs: the same instance.yaml filters identically on
    # macOS and Linux, and patterns match the on-disk name, not the tool key.
    home, inst = _machine(
        tmp_path,
        "footprint:\n"
        "  ignore: [.Weird*]\n"
        "  roots:\n    - {label: xdg-config, path: ~/.config}\n",
    )
    (home / ".config" / ".weirdtool").mkdir()
    out = _observe(tmp_path, inst)
    # The pattern names .Weird*; the on-disk name is .weirdtool: no match,
    # on either OS, regardless of filesystem case rules.
    assert "weirdtool" in out
    [fp] = out["weirdtool"].facts["footprints"]
    assert fp["path"] == "~/.config/.weirdtool"


def test_a_malformed_ignore_raises(tmp_path):
    home, inst = _machine(
        tmp_path,
        "footprint:\n  ignore: [3]\n  roots:\n"
        "    - {label: xdg-config, path: ~/.config}\n",
    )
    with pytest.raises(ValueError, match="ignore"):
        ADAPTER.observe(_ctx(tmp_path, inst))


def test_an_unknown_footprint_section_key_raises(tmp_path):
    home, inst = _machine(
        tmp_path,
        "footprint:\n  ignroe: [x]\n  roots:\n"
        "    - {label: xdg-config, path: ~/.config}\n",
    )
    with pytest.raises(ValueError, match="ignroe"):
        ADAPTER.observe(_ctx(tmp_path, inst))


def test_a_tool_matching_another_adapters_entry_is_attributed(tmp_path):
    home, inst = _machine(tmp_path)
    ctx = _ctx(tmp_path, inst, entries=[_entry("pkg-brew/gh", "pkg-brew")])
    out = {o.native_id: o for o in ADAPTER.observe(ctx)}
    assert out["gh"].facts["governed_by"] == "pkg-brew/gh"
    assert "governed_by" not in out["uv"].facts  # no entry, no attribution


def test_attribution_normalizes_the_entry_native_id(tmp_path):
    # chezmoi/.zshrc governs the ~/.zshrc trace: the dot and case fold away
    # on the entry side exactly as they do for the tool key.
    home, inst = _machine(
        tmp_path,
        'footprint:\n  roots:\n    - {label: home-dot, path: "~", dot_only: true}\n',
    )
    (home / ".zshrc").write_text("")
    ctx = _ctx(tmp_path, inst, entries=[_entry("chezmoi/.zshrc", "chezmoi")])
    out = {o.native_id: o for o in ADAPTER.observe(ctx)}
    assert out["zshrc"].facts["governed_by"] == "chezmoi/.zshrc"


def test_a_footprint_entry_never_attributes_itself(tmp_path):
    # A declared footprint/gh already keeps gh out of ungoverned by id; the
    # attribution seam exists for OTHER adapters' entries only.
    home, inst = _machine(tmp_path)
    ctx = _ctx(tmp_path, inst, entries=[_entry("footprint/gh", "footprint")])
    out = {o.native_id: o for o in ADAPTER.observe(ctx)}
    assert "governed_by" not in out["gh"].facts


def test_a_retired_owner_still_attributes(tmp_path):
    # The retired entry IS the decision; its own adapter alerts on the
    # lingering package, and the trace must not pile a second question on top.
    home, inst = _machine(tmp_path)
    entry = entry_from_dict(
        {"id": "pkg-brew/gh", "adapter": "pkg-brew", "domain": "package",
         "lifecycle": "retired", "intent": "i"}
    )  # fmt: skip
    ctx = _ctx(tmp_path, inst, entries=[entry])
    out = {o.native_id: o for o in ADAPTER.observe(ctx)}
    assert out["gh"].facts["governed_by"] == "pkg-brew/gh"


def test_attribution_is_deterministic_across_multiple_matches(tmp_path):
    home, inst = _machine(tmp_path)
    ctx = _ctx(
        tmp_path,
        inst,
        entries=[
            _entry("pkg-brew/gh", "pkg-brew"),
            _entry("manual/gh", "manual"),
        ],
    )
    out = {o.native_id: o for o in ADAPTER.observe(ctx)}
    assert out["gh"].facts["governed_by"] == "manual/gh"  # first by sorted id


# ---- lifecycle flows: adapter facts through the real triage ---------------


def _lifecycle_report(tmp_path, lifecycle, tool="gh"):
    from planeops.core.drift import triage

    tmp_path.mkdir(parents=True, exist_ok=True)
    home, inst = _machine(tmp_path)
    entry = entry_from_dict(
        {"id": f"footprint/{tool}", "adapter": "footprint",
         "domain": "footprint", "lifecycle": lifecycle, "intent": "i"}
    )  # fmt: skip
    obs = {o.key: o for o in ADAPTER.observe(_ctx(tmp_path, inst, entries=[entry]))}
    return triage([entry], obs, {"footprint"})


def test_an_active_present_footprint_is_conformant(tmp_path):
    rep = _lifecycle_report(tmp_path, "active")
    assert not rep.alerts and not rep.report
    assert "footprint/gh" not in [i.entry_id for i in rep.ungoverned]


def test_an_active_absent_footprint_alerts(tmp_path):
    rep = _lifecycle_report(tmp_path, "active", tool="ghost")
    assert [a.entry_id for a in rep.alerts] == ["footprint/ghost"]
    assert "present" in rep.alerts[0].message


def test_a_parked_present_footprint_is_silent(tmp_path):
    rep = _lifecycle_report(tmp_path / "a", "parked")
    assert not rep.alerts and not rep.report


def test_a_parked_vanished_footprint_reports_without_alerting(tmp_path):
    # The engine's cross-adapter semantics: a parked thing that disappeared
    # entirely earns a report line (never an alert), same as a parked service.
    rep = _lifecycle_report(tmp_path / "b", "parked", tool="ghost")
    assert not rep.alerts
    assert any("parked but not observed" in i.message for i in rep.report)


def test_a_retired_footprint_still_present_alerts(tmp_path):
    rep = _lifecycle_report(tmp_path, "retired")
    assert [a.entry_id for a in rep.alerts] == ["footprint/gh"]
    assert "retired" in rep.alerts[0].message


def test_a_completed_retirement_asks_for_registry_cleanup(tmp_path):
    rep = _lifecycle_report(tmp_path, "retired", tool="ghost")
    assert not rep.alerts
    assert any(
        i.entry_id == "footprint/ghost" and "remove the entry" in i.message
        for i in rep.report
    )


def test_the_adapter_is_discovered_and_observe_only(tmp_path):
    from planeops.core.discovery import discover_adapters

    adapter = discover_adapters().get("footprint")
    assert isinstance(adapter, FootprintAdapter)
    assert not hasattr(adapter, "plan") and not hasattr(adapter, "execute")
