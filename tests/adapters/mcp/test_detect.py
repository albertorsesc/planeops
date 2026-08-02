"""Detection mechanism: config + installed client required; no client named."""

from planeops.adapters.mcp.detect import detect_sources


def _nowhich(name):
    return None


def test_detects_only_installed_clients_with_configs(tmp_path):
    (tmp_path / ".claude.json").write_text("{}")
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text("")
    apps = tmp_path / "Applications"
    apps.mkdir()
    found = detect_sources(
        tmp_path,
        which=lambda n: "/x/claude" if n == "claude" else None,
        app_root=apps,
    )
    labels = [f["label"] for f in found]
    assert labels == ["claude-code"]  # codex config exists but no binary


def test_a_config_remnant_without_the_client_is_not_detected(tmp_path):
    # A config directory can outlive its uninstalled client (a real machine
    # had ~/.codex and ~/.cursor exactly so). Wiring a dead client's config
    # overstates reality; detection requires the CLIENT, not just its config.
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text("")
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor" / "mcp.json").write_text("{}")
    assert detect_sources(tmp_path, which=_nowhich, app_root=tmp_path) == []


def test_client_presence_via_app_bundle(tmp_path):
    cfg = tmp_path / "Library" / "Application Support" / "Claude"
    cfg.mkdir(parents=True)
    (cfg / "claude_desktop_config.json").write_text("{}")
    apps = tmp_path / "Applications"
    (apps / "Claude.app").mkdir(parents=True)
    found = detect_sources(tmp_path, which=_nowhich, app_root=apps)
    desktop = next(f for f in found if f["label"] == "claude-desktop")
    assert "{name}" in desktop["logs"]


def test_empty_disk_detects_nothing(tmp_path):
    assert detect_sources(tmp_path, which=_nowhich, app_root=tmp_path) == []
