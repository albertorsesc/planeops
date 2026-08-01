"""The redaction gate: a secret value is unreachable outside the secrets adapter's
execute, and never reaches a snapshot, a report, or the journal.
"""

from datetime import datetime

import pytest

from planeops.adapters.secrets import SecretsAdapter
from planeops.core.apply import run_apply
from planeops.core.contracts import Change, Result
from planeops.core.observe import run_observe
from planeops.secrets import RedactionError

VALUE = "sk-super-secret-value"


class FakeBackend:
    name = "fake"

    def __init__(self, present):
        self._present = set(present)

    def exists(self, name):
        return name in self._present

    def meta(self, name):
        return {"configured": True} if name in self._present else None

    def get(self, name):
        return VALUE


def _seed(tmp_path, extra=""):
    reg = tmp_path / "registry"
    reg.mkdir(exist_ok=True)
    (reg / "machine.yaml").write_text(
        "entries:\n"
        "  - {id: manual/x, adapter: manual, domain: host, lifecycle: active, intent: i}\n"
        + extra
    )


_CONSUMER = (
    "  - id: secrets/openrouter-api-key\n"
    "    adapter: secrets\n"
    "    domain: secret\n"
    "    lifecycle: active\n"
    "    intent: the secret\n"
    "  - id: launchd/gw\n"
    "    adapter: launchd\n"
    "    domain: service\n"
    "    lifecycle: active\n"
    "    phase: 6\n"
    "    intent: consumer\n"
    "    secrets:\n"
    "      - ref: secret://sops/openrouter-api-key\n"
    "        injected_as: file:{target}#OPENROUTER_API_KEY\n"
)


def test_value_is_unreachable_during_observe(tmp_path, fake_platform):
    _seed(tmp_path)
    captured = {}

    class Spy:
        name = "spy"
        domains = ("secret",)
        default_phase = 5

        def observe(self, ctx):
            captured["handle"] = ctx.secrets
            return []

    run_observe(
        tmp_path,
        now=datetime(2026, 7, 28),
        platform=fake_platform(tmp_path),
        adapters={"spy": Spy()},
    )
    handle = captured["handle"]
    assert handle is not None
    assert not hasattr(handle, "unsealed")  # no value escape hatch on ctx.secrets
    with pytest.raises(RedactionError):
        handle.get("anything")


def test_adapter_reading_a_value_during_observe_fails_rather_than_leaks(
    tmp_path, fake_platform
):
    _seed(tmp_path)

    class Leaky:
        name = "leaky"
        domains = ("secret",)
        default_phase = 5

        def observe(self, ctx):
            ctx.secrets.get("x")  # attempting a value here must raise, not leak
            return []

    snap = run_observe(
        tmp_path,
        now=datetime(2026, 7, 28),
        platform=fake_platform(tmp_path),
        adapters={"leaky": Leaky()},
    )
    assert any(f["adapter"] == "leaky" for f in snap["failed"])
    assert snap["observed"] == []
    assert (
        VALUE not in (tmp_path / "observed" / "testhost" / "snapshot.json").read_text()
    )


def test_non_secret_adapter_execute_cannot_obtain_a_value(tmp_path, fake_platform):
    _seed(
        tmp_path,
        extra=(
            "  - id: spy/thing\n"
            "    adapter: spy\n"
            "    domain: service\n"
            "    lifecycle: active\n"
            "    intent: a non-secret adapter that tries to read a secret\n"
        ),
    )

    class LeakySpy:
        name = "spy"
        domains = ("service",)
        default_phase = 6

        def observe(self, ctx):
            return []

        def plan(self, entry, obs, ctx=None):
            return [Change(entry.id, "configure", "spy change", {})]

        def execute(self, change, ctx):
            value = ctx.secrets.get("openrouter-api-key")  # not a secret adapter
            return Result(ok=True, detail=f"leaked {value}")

    plat = fake_platform(tmp_path)
    adapters = {"spy": LeakySpy()}
    run_observe(tmp_path, now=datetime(2026, 7, 28), platform=plat, adapters=adapters)
    applied = run_apply(
        tmp_path,
        platform=plat,
        adapters=adapters,
        confirm=lambda change: "y",
        now=datetime(2026, 7, 28),
        secrets_store=FakeBackend(["openrouter-api-key"]),
    )
    assert applied and applied[0].result.ok is False  # get() raised, execute failed
    journal = (tmp_path / "observed" / "testhost" / "applied.jsonl").read_text()
    assert VALUE not in journal


def test_apply_materializes_the_value_without_journaling_it(tmp_path, fake_platform):
    target = tmp_path / "svc" / "env"
    _seed(tmp_path, extra=_CONSUMER.format(target=target))
    plat = fake_platform(tmp_path)
    adapters = {"secrets": SecretsAdapter()}  # launchd absent -> consumer is skipped

    run_observe(tmp_path, now=datetime(2026, 7, 28), platform=plat, adapters=adapters)
    applied = run_apply(
        tmp_path,
        platform=plat,
        adapters=adapters,
        confirm=lambda change: "y",
        now=datetime(2026, 7, 28),
        secrets_store=FakeBackend(["openrouter-api-key"]),
    )

    assert [a.executed and a.result.ok for a in applied] == [True]
    assert target.read_text() == f"OPENROUTER_API_KEY={VALUE}\n"  # value only here
    journal = (tmp_path / "observed" / "testhost" / "applied.jsonl").read_text()
    assert VALUE not in journal


def test_id_filtered_apply_still_materializes_a_cross_phase_consumer(
    tmp_path, fake_platform
):
    # `plane apply --id secrets/...` narrows what converges but must still see the
    # phase-6 consumer to materialize into it (regression: ctx.entries was filtered).
    target = tmp_path / "svc" / "env"
    _seed(tmp_path, extra=_CONSUMER.format(target=target))
    plat = fake_platform(tmp_path)
    adapters = {"secrets": SecretsAdapter()}

    run_observe(tmp_path, now=datetime(2026, 7, 28), platform=plat, adapters=adapters)
    applied = run_apply(
        tmp_path,
        only_id="secrets/openrouter-api-key",
        platform=plat,
        adapters=adapters,
        confirm=lambda change: "y",
        now=datetime(2026, 7, 28),
        secrets_store=FakeBackend(["openrouter-api-key"]),
    )

    assert [a.executed and a.result.ok for a in applied] == [True]
    assert target.read_text() == f"OPENROUTER_API_KEY={VALUE}\n"
