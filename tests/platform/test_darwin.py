"""macOS platform impl: host identity and home."""

from pathlib import Path

from engine.platform.darwin import PlatformDarwin


def test_hostname_strips_the_bonjour_local_suffix(monkeypatch):
    monkeypatch.setattr("socket.gethostname", lambda: "host.local")
    assert PlatformDarwin().hostname() == "host"  # observed/<host>/ stays clean


def test_hostname_without_suffix_is_untouched(monkeypatch):
    monkeypatch.setattr("socket.gethostname", lambda: "workstation")
    assert PlatformDarwin().hostname() == "workstation"


def test_home_is_a_path():
    assert isinstance(PlatformDarwin().home(), Path)
