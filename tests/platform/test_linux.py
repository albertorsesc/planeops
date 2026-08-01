"""Linux platform impl: host identity and home."""

from pathlib import Path

from engine.platform.linux import PlatformLinux


def test_hostname_is_untouched(monkeypatch):
    # No `.local` strip: that suffix is a macOS Bonjour artifact, and a Linux
    # host legitimately named that way must keep its name.
    monkeypatch.setattr("socket.gethostname", lambda: "host.local")
    assert PlatformLinux().hostname() == "host.local"


def test_home_is_a_path():
    assert isinstance(PlatformLinux().home(), Path)
