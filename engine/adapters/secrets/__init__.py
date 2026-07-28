"""secrets adapter (presence only).

observe reports, for each declared `secrets/<name>` entry, whether that secret is
configured in the backend, and nothing more: `facts.configured` is a boolean, never
a value. The backend defaults to a sops store at `registry/secrets.sops.yaml` under
the instance root, overridable via `instance.yaml`'s `secrets.store`; tests inject
a backend directly.

This adapter is observe-only. Materialization (injecting a secret at apply time)
and the `ctx.secrets` redaction gate are a later slice; keeping observe presence-
only means no secret value can reach a snapshot or report today.
"""

from __future__ import annotations

from engine.config import section as instance_section
from engine.core.contracts import Ctx, Observed
from engine.secrets import SecretsBackend
from engine.secrets.sops import SopsBackend

DEFAULT_STORE = "registry/secrets.sops.yaml"


class SecretsAdapter:
    name = "secrets"
    domains: tuple[str, ...] = ("secret",)

    def __init__(self, backend: SecretsBackend | None = None):
        self._backend = backend

    def observe(self, ctx: Ctx) -> list[Observed]:
        backend = self._backend
        if backend is None:
            if ctx.repo_root is None:
                return []
            configured = instance_section(ctx.repo_root, "secrets").get("store")
            rel = (
                configured
                if isinstance(configured, str) and configured
                else DEFAULT_STORE
            )
            backend = SopsBackend(ctx.repo_root / rel)
        return [
            Observed(
                adapter=self.name,
                native_id=entry.native_id,
                facts={"configured": backend.exists(entry.native_id)},
                version=None,
            )
            for entry in ctx.entries
            if entry.adapter == self.name
        ]


ADAPTER = SecretsAdapter()
