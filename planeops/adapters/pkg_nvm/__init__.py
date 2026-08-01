"""pkg-nvm adapter (node runtimes installed via nvm).

observe reports the node versions present under nvm's install directory
(`~/.nvm/versions/node`). This adapter is observe-only: nvm is a shell function,
not a binary, so there is no clean subprocess seam to install or uninstall
versions. Converging node versions stays manual for now.

Filesystem access goes through the platform seam, so the adapter is testable
against a temp directory and never reads the real machine under test.
"""

from __future__ import annotations

from pathlib import Path

from planeops.core.contracts import Ctx, Observed


class PkgNvmAdapter:
    name = "pkg-nvm"
    domains: tuple[str, ...] = ("runtime",)

    def __init__(self, nvm_dir: Path | None = None):
        self._nvm_dir_override = nvm_dir

    def _node_dir(self, ctx: Ctx) -> Path:
        if self._nvm_dir_override is not None:
            return self._nvm_dir_override
        return ctx.platform.home() / ".nvm" / "versions" / "node"

    def observe(self, ctx: Ctx) -> list[Observed]:
        node_dir = self._node_dir(ctx)
        if not node_dir.is_dir():
            return []
        out: list[Observed] = []
        for child in sorted(node_dir.iterdir()):
            if not child.is_dir():
                continue
            version = child.name[1:] if child.name.startswith("v") else child.name
            out.append(
                Observed(
                    adapter=self.name, native_id=version, facts={}, version=version
                )
            )
        return out


ADAPTER = PkgNvmAdapter()
