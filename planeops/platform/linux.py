"""Linux platform contract implementation.

Host identity and standard paths only, the same three members as the macOS impl.
There is deliberately no scheduler here: the Platform contract carries none (launchd
is the darwin adapter's concern), so the OS-neutral domains (packages, config,
secrets) run on Linux while service reproduction stays macOS-specific.
"""

from __future__ import annotations

import socket
from pathlib import Path


class PlatformLinux:
    name = "linux"
    sys_platforms: tuple[str, ...] = ("linux",)

    def hostname(self) -> str:
        # No `.local` strip: that suffix is a macOS Bonjour artifact.
        return socket.gethostname()

    def home(self) -> Path:
        return Path.home()


PLATFORM = PlatformLinux()
