import pytest


class _FakePlatform:
    """A Platform whose home and hostname are fixed, so adapters and the
    observe/drift loop can be exercised without touching the real machine."""

    name = "fake"

    def __init__(self, home):
        self._home = home

    def hostname(self) -> str:
        return "testhost"

    def home(self):
        return self._home


@pytest.fixture
def fake_platform():
    """Return a factory: `fake_platform(home)` -> a Platform rooted at `home`."""
    return _FakePlatform
