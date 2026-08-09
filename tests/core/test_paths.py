"""Configured-path resolution: home comes from the platform, never the process."""

from pathlib import Path

from planeops.core.paths import resolve_path

HOME = Path("/fake/home")


def test_bare_tilde_is_the_platform_home():
    assert resolve_path("~", HOME) == HOME


def test_tilde_slash_resolves_under_the_platform_home():
    assert resolve_path("~/.config/gh", HOME) == HOME / ".config/gh"


def test_absolute_paths_pass_through():
    assert resolve_path("/etc/hosts", HOME) == Path("/etc/hosts")


def test_a_tilde_username_form_is_not_expanded():
    # Only the calling user's home is known to the platform; `~other` stays
    # literal rather than guessing at the process environment.
    assert resolve_path("~other/x", HOME) == Path("~other/x")
