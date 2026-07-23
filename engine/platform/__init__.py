"""Platform seam: one implementation per OS behind the Platform contract."""

from __future__ import annotations

import sys

from engine.core.contracts import Platform


def current_platform() -> Platform:
    """Return the platform implementation for the host OS."""
    if sys.platform == "darwin":
        from engine.platform.darwin import PlatformDarwin

        return PlatformDarwin()
    raise NotImplementedError(f"no platform implementation for {sys.platform!r} yet")
