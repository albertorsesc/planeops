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


def test_a_relative_path_is_refused():
    # It would resolve against the process CWD, so observations would depend
    # on where the command ran.
    import pytest

    with pytest.raises(ValueError, match="absolute or start with"):
        resolve_path(".config", HOME)


def test_a_tilde_username_form_is_refused():
    # Only the calling user's home is known to the platform; `~other` has no
    # home to borrow and would otherwise become a relative literal path.
    import pytest

    with pytest.raises(ValueError, match="absolute or start with"):
        resolve_path("~other/x", HOME)
