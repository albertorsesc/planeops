"""The manual adapter ships in core (SPEC.md section 4).

observe = an attestation recorded in observed state; there is no execute. It is
reserved for assets with no planned adapter. Rows whose real adapter is merely
unbuilt keep the real adapter name and surface under DRIFT's Uncovered section.

Attestation prompts run only in an interactive `plane observe --attest`. In
non-TTY runs (the scheduled slot) manual reuses the last attestation and marks
it stale after 30 days; a stale attestation is report-level drift.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from planeops.core.contracts import Ctx, Observed
from planeops.core.schema import Entry

STALE_AFTER = timedelta(days=30)


class ManualAdapter:
    name = "manual"
    domains: tuple[str, ...] = ()  # open: manual can stand in for any domain

    def observe(self, ctx: Ctx) -> list[Observed]:
        out: list[Observed] = []
        for entry in ctx.entries:
            if entry.adapter != self.name:
                continue
            out.append(self._attest(entry, ctx))
        return out

    def _attest(self, entry: Entry, ctx: Ctx) -> Observed:
        prior = ctx.prior.get(entry.id)

        # `--attest` records a fresh attestation. Without it (the scheduled
        # slot) manual reuses the last one and lets it age into staleness.
        if ctx.attest:
            attested_at: str | None = ctx.now.isoformat()
            stale = False
        else:
            attested_at = prior.facts.get("attested_at") if prior else None
            stale = _is_stale(attested_at, ctx.now)

        return Observed(
            adapter=self.name,
            native_id=entry.native_id,
            facts={"attested_at": attested_at, "stale": stale},
            version=None,
        )


def _is_stale(attested_at: str | None, now: datetime) -> bool:
    if not attested_at:
        return True  # never attested is stale
    try:
        when = datetime.fromisoformat(attested_at)
    except ValueError:
        return True
    return (now - when) > STALE_AFTER


ADAPTER = ManualAdapter()
