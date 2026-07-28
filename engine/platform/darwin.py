"""macOS platform contract implementation.

Provides host identity and standard paths. Scheduler and process-listing helpers
can be added here when an adapter needs them; launchd access currently lives in
the launchd adapter behind its own injected command seam.
"""

from __future__ import annotations

import socket
from pathlib import Path


class PlatformDarwin:
    name = "darwin"
    sys_platforms: tuple[str, ...] = ("darwin",)

    def hostname(self) -> str:
        # Local, stable host label. Strip the .local suffix Bonjour appends so
        # the observed/<host>/ directory name stays clean across networks.
        return socket.gethostname().removesuffix(".local")

    def home(self) -> Path:
        return Path.home()


PLATFORM = PlatformDarwin()
