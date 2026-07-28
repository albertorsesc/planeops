import sys
from pathlib import Path

import pytest

from engine.core.contracts import Platform
from engine.platform import current_platform, discover_platforms
from engine.platform.darwin import PlatformDarwin
from engine.platform.linux import PlatformLinux


def test_discovers_the_os_impls():
    assert {"darwin", "linux"} <= {p.name for p in discover_platforms()}


def test_discovered_platforms_satisfy_the_contract():
    for p in discover_platforms():
        assert isinstance(p, Platform)
        assert isinstance(p.hostname(), str) and p.hostname()
        assert isinstance(p.home(), Path)


def test_current_platform_selects_by_host(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert current_platform().name == "darwin"
    monkeypatch.setattr(sys, "platform", "linux")
    assert current_platform().name == "linux"


def test_unknown_os_raises(monkeypatch):
    monkeypatch.setattr(sys, "platform", "sunos5")
    with pytest.raises(NotImplementedError):
        current_platform()


def test_darwin_strips_local_suffix_linux_does_not(monkeypatch):
    monkeypatch.setattr("socket.gethostname", lambda: "host.local")
    assert PlatformDarwin().hostname() == "host"  # Bonjour suffix stripped
    assert PlatformLinux().hostname() == "host.local"  # kept on Linux
