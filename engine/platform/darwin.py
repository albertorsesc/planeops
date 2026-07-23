"""macOS platform contract implementation.

M1 needs only host identity and standard paths. Scheduler (launchd load/unload/
list) and process listing arrive with the launchd adapter in M2.
"""

from __future__ import annotations

import socket
from pathlib import Path


class PlatformDarwin:
    name = "darwin"

    def hostname(self) -> str:
        # Local, stable host label. Strip the .local suffix Bonjour appends so
        # the observed/<host>/ directory name stays clean across networks.
        return socket.gethostname().removesuffix(".local")

    def home(self) -> Path:
        return Path.home()
