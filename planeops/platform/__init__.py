"""Platform seam: one implementation per OS behind the Platform contract.

Each OS module under `engine/platform/` exposes a module-level `PLATFORM` (an impl
of the `Platform` contract) that declares the `sys.platform` prefixes it serves.
`current_platform()` selects the one matching the host by scanning, the same
package-scan/no-central-list discipline adapters and importers use, so adding an
OS is dropping a module in, not editing a dispatch.
"""

from __future__ import annotations

import sys

from planeops.core.contracts import Platform


def discover_platforms() -> list[Platform]:
    """Every `planeops.platform.<os>` exposing a module-level `PLATFORM`."""
    import planeops.platform
    from planeops.core.discovery import discover

    found = discover(
        planeops.platform,
        "PLATFORM",
        Platform,  # type: ignore[type-abstract]  # isinstance-only, see discover()
    )
    return list(found.values())


def _serves(platform: Platform, host: str) -> bool:
    # Each impl declares `sys_platforms`: the sys.platform prefixes it handles.
    selectors: tuple[str, ...] = getattr(platform, "sys_platforms", ())
    return any(host == s or host.startswith(s) for s in selectors)


def current_platform() -> Platform:
    """The platform implementation for the host OS, selected by discovery."""
    for platform in discover_platforms():
        if _serves(platform, sys.platform):
            return platform
    raise NotImplementedError(f"no platform implementation for {sys.platform!r} yet")
