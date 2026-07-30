"""`plane init`: scaffold an instance and register it in the home config dir.

config_dir is injected so nothing here touches the real ~/.config.
"""

import tomllib
from pathlib import Path

from engine.cli import main
from engine.core.init import init_instance


def test_init_scaffolds_the_instance_and_registers_it(tmp_path):
    inst = tmp_path / "inst"
    cfg = tmp_path / "cfg" / "planeops"
    actions = init_instance(inst, cfg)
    assert (inst / ".planeops").exists()  # discovery marker
    assert (inst / "registry").is_dir()
    # the scaffolded instance.yaml is the shipped commented reference, not a stub
    body = (inst / "instance.yaml").read_text()
    assert "how this machine's adapters read" in body and "mcp:" in body
    data = tomllib.loads((cfg / "config.toml").read_text())
    assert Path(data["instance"]) == inst.resolve()  # absolute, resolved pointer
    assert actions  # reports what it did


def test_init_keeps_existing_files(tmp_path):
    inst = tmp_path / "inst"
    cfg = tmp_path / "cfg" / "planeops"
    init_instance(inst, cfg)
    (inst / "instance.yaml").write_text("mine: 1\n")  # user-edited
    init_instance(inst, cfg)  # second run
    assert (inst / "instance.yaml").read_text() == "mine: 1\n"  # not clobbered


def test_init_does_not_repoint_config_without_force(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    cfg = tmp_path / "cfg" / "planeops"
    init_instance(one, cfg)
    init_instance(two, cfg)  # different instance, no force
    data = tomllib.loads((cfg / "config.toml").read_text())
    assert Path(data["instance"]) == one.resolve()  # first pointer preserved
    init_instance(two, cfg, force=True)
    data = tomllib.loads((cfg / "config.toml").read_text())
    assert Path(data["instance"]) == two.resolve()  # force repoints


def test_cli_init_no_seed_scaffolds_only(tmp_path, monkeypatch):
    # config_home() honors XDG_CONFIG_HOME, so the real ~/.config is never touched.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    inst = tmp_path / "inst"
    assert main(["init", str(inst), "--no-seed"]) == 0
    assert (inst / ".planeops").exists() and (inst / "instance.yaml").is_file()
    assert not (inst / "registry" / "imported.yaml").exists()  # not seeded


def test_cli_init_seed_populates_registry_from_the_machine(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    def fake_observe(repo, **k):  # a controlled machine scan (no real observe)
        return {
            "host": "h",
            "observed": [
                {"adapter": "ollama", "native_id": "m1", "facts": {}},
                {"adapter": "mcp", "native_id": "c7", "facts": {}},
            ],
        }

    monkeypatch.setattr("engine.core.observe.run_observe", fake_observe)
    inst = tmp_path / "inst"
    assert main(["init", str(inst), "--seed"]) == 0
    from engine.core.registry import load_registry

    ids = {e.id for e in load_registry(inst / "registry").entries}
    assert ids == {"ollama/m1", "mcp/c7"}  # one command -> a governed registry


def test_after_init_the_resolver_finds_the_instance(tmp_path):
    # End-to-end: init writes the pointer, resolve_instance_root reads it back.
    from engine.core.locate import resolve_instance_root

    inst = tmp_path / "inst"
    xdg = tmp_path / "xdgcfg"
    init_instance(inst, xdg / "planeops")
    got = resolve_instance_root(
        None, env={"XDG_CONFIG_HOME": str(xdg)}, home=tmp_path, cwd=tmp_path
    )
    assert got == inst.resolve()
