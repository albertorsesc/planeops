"""Known-client detection: the tool wires its own sources."""

from planeops.adapters.mcp.detect import detect_sources


def test_detects_only_clients_present_on_disk(tmp_path):
    (tmp_path / ".claude.json").write_text("{}")
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text("")
    found = detect_sources(tmp_path)
    labels = [f["label"] for f in found]
    assert "claude-code" in labels and "codex" in labels
    assert "claude-desktop" not in labels  # not on this fake disk
    codex = next(f for f in found if f["label"] == "codex")
    assert codex["format"] == "toml" and codex["key"] == "mcp_servers"


def test_desktop_detection_carries_its_log_template(tmp_path):
    cfg = tmp_path / "Library" / "Application Support" / "Claude"
    cfg.mkdir(parents=True)
    (cfg / "claude_desktop_config.json").write_text("{}")
    found = detect_sources(tmp_path)
    desktop = next(f for f in found if f["label"] == "claude-desktop")
    assert "{name}" in desktop["logs"]


def test_empty_disk_detects_nothing(tmp_path):
    assert detect_sources(tmp_path) == []
