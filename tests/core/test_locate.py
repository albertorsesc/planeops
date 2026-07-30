"""Instance-root resolution and discovery.

Precedence: --repo > $PLANEOPS_INSTANCE > ~/.config/planeops/config.toml > cwd.
Discovery anchors solely on a `.planeops` marker. env / home / cwd are injected so
nothing here touches the real machine.
"""

from engine.core.locate import config_home, find_repo_root, resolve_instance_root


def _marker(p):
    p.mkdir(parents=True, exist_ok=True)
    (p / ".planeops").write_text("")
    return p.resolve()


def test_find_repo_root_finds_the_planeops_marker(tmp_path):
    root = tmp_path / "inst"
    (root / "sub" / "deep").mkdir(parents=True)
    (root / ".planeops").write_text("")
    assert find_repo_root(root / "sub" / "deep") == root


def test_find_repo_root_falls_back_to_start_without_a_marker(tmp_path):
    # No `.planeops` anywhere up the tree -> `start` is treated as the root. (No
    # legacy SPEC.md/registry anchor: the marker is the only beacon.)
    (tmp_path / "registry").mkdir()
    assert find_repo_root(tmp_path) == tmp_path


def test_config_home_honors_xdg_then_home(tmp_path):
    assert config_home(env={"XDG_CONFIG_HOME": str(tmp_path)}) == tmp_path / "planeops"
    assert config_home(env={}, home=tmp_path) == tmp_path / ".config" / "planeops"


def test_cli_repo_wins_over_env_and_config(tmp_path):
    explicit = _marker(tmp_path / "explicit")
    env = {"PLANEOPS_INSTANCE": str(_marker(tmp_path / "fromenv"))}
    got = resolve_instance_root(str(explicit), env=env, home=tmp_path, cwd=tmp_path)
    assert got == explicit


def test_env_used_when_no_cli_repo(tmp_path):
    fromenv = _marker(tmp_path / "fromenv")
    got = resolve_instance_root(
        None, env={"PLANEOPS_INSTANCE": str(fromenv)}, home=tmp_path, cwd=tmp_path
    )
    assert got == fromenv


def test_config_toml_used_when_no_cli_or_env(tmp_path):
    inst = _marker(tmp_path / "frominst")
    cfg = tmp_path / ".config" / "planeops"
    cfg.mkdir(parents=True)
    (cfg / "config.toml").write_text(f'instance = "{inst}"\n')
    got = resolve_instance_root(None, env={}, home=tmp_path, cwd=tmp_path)
    assert got == inst


def test_cwd_is_the_last_resort(tmp_path):
    cwd = _marker(tmp_path / "cwdinst")
    got = resolve_instance_root(None, env={}, home=tmp_path, cwd=cwd)
    assert got == cwd


def test_malformed_or_empty_config_toml_is_ignored(tmp_path):
    cfg = tmp_path / ".config" / "planeops"
    cfg.mkdir(parents=True)
    cwd = _marker(tmp_path / "cwdinst")
    for bad in ("{ not toml", "", "other = 1\n"):  # invalid, empty, no `instance`
        (cfg / "config.toml").write_text(bad)
        # falls through to cwd, never raises
        assert resolve_instance_root(None, env={}, home=tmp_path, cwd=cwd) == cwd
