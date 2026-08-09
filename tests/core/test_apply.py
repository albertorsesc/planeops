"""Apply loop: the engine owns confirmation. Exercised with a fake mutating
adapter and a scripted confirm, so nothing here touches the machine.
"""

import json
from datetime import datetime

import pytest

from planeops.core.apply import run_apply
from planeops.core.contracts import Change, Result

REG = (
    "entries:\n"
    "  - {id: fake/a, adapter: fake, domain: d, lifecycle: active, intent: i}\n"
    "  - {id: fake/b, adapter: fake, domain: d, lifecycle: active, intent: i}\n"
)


class FakeMutating:
    name = "fake"
    domains = ("d",)
    default_phase = 1  # required by the MutatingAdapter contract

    def __init__(self, changes_by_entry):
        self._changes = changes_by_entry
        self.executed = []

    def observe(self, ctx):
        return []

    def plan(self, entry, obs, ctx=None):
        return self._changes.get(entry.id, [])

    def execute(self, change, ctx):
        self.executed.append(change)
        return Result(ok=True, detail="done")


class FakeObserveOnly:
    name = "fake"
    domains = ("d",)

    def observe(self, ctx):
        return []


class FakeRaisingExecute:
    name = "fake"
    domains = ("d",)
    default_phase = 1

    def observe(self, ctx):
        return []

    def plan(self, entry, obs, ctx=None):
        return [CA] if entry.id == "fake/a" else []

    def execute(self, change, ctx):
        raise RuntimeError("execute boom")


def _scripted(answers):
    it = iter(answers)
    return lambda change: next(it)


def _seed(tmp_path, reg=REG):
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "r.yaml").write_text(reg)
    obs = tmp_path / "observed" / "testhost"
    obs.mkdir(parents=True)
    (obs / "snapshot.json").write_text(
        json.dumps(
            {
                "host": "testhost",
                "ts": "t",
                "engine_version": "0",
                "observed": [],
                "uncovered": [],
            }
        )
    )


CA = Change("fake/a", "configure", "do a", {"n": 1})
CB = Change("fake/b", "configure", "do b", {"n": 2})


def _run(tmp_path, fake_platform, adapters, answers, **kw):
    return run_apply(
        tmp_path,
        platform=fake_platform(tmp_path),
        adapters=adapters,
        confirm=_scripted(answers),
        now=datetime(2026, 7, 22),
        **kw,
    )


def test_yes_executes_no_skips(tmp_path, fake_platform):
    _seed(tmp_path)
    fake = FakeMutating({"fake/a": [CA], "fake/b": [CB]})
    applied = _run(tmp_path, fake_platform, {"fake": fake}, ["y", "n"])
    assert fake.executed == [CA]
    assert [(a.change.entry_id, a.executed) for a in applied] == [
        ("fake/a", True),
        ("fake/b", False),
    ]


def test_unphased_entries_converge_by_adapter_default_phase(tmp_path, fake_platform):
    # Unphased entries inherit each adapter's contract-declared default_phase
    # (now REQUIRED on MutatingAdapter): the secret-like adapter (5) converges
    # before the service-like one (6), though the registry lists the service
    # first.
    reg = (
        "entries:\n"
        "  - {id: svc/x, adapter: svc, domain: s, lifecycle: active, intent: i}\n"
        "  - {id: sec/y, adapter: sec, domain: sd, lifecycle: active, intent: i}\n"
    )
    _seed(tmp_path, reg)
    order = []

    class Recorder:
        def __init__(self, name, domain, **kw):
            self.name, self.domains = name, (domain,)
            for k, v in kw.items():
                setattr(self, k, v)

        def observe(self, ctx):
            return []

        def plan(self, entry, obs, ctx=None):
            return [Change(entry.id, "configure", "d", {})]

        def execute(self, change, ctx):
            order.append(change.entry_id)
            return Result(ok=True, detail="")

    adapters = {
        "sec": Recorder("sec", "sd", default_phase=5),
        "svc": Recorder("svc", "s", default_phase=6),  # services load last
    }
    _run(tmp_path, fake_platform, adapters, ["y", "y"])
    assert order == ["sec/y", "svc/x"]


def test_all_in_domain_auto_approves_rest(tmp_path, fake_platform):
    _seed(tmp_path)
    fake = FakeMutating({"fake/a": [CA], "fake/b": [CB]})
    # Only one answer: 'a' on the first change auto-approves the rest of domain d.
    applied = _run(tmp_path, fake_platform, {"fake": fake}, ["a"])
    assert fake.executed == [CA, CB]
    assert all(a.executed for a in applied)


def test_auto_approved_changes_still_render_their_diffs(
    tmp_path, fake_platform, capsys
):
    # 'a' answers the question for the domain, not the showing: a change that
    # executes under a standing 'a' must still put its diff on the screen, or
    # the engine's no-unseen-mutation promise breaks.
    _seed(tmp_path)
    fake = FakeMutating({"fake/a": [CA], "fake/b": [CB]})
    _run(tmp_path, fake_platform, {"fake": fake}, ["a"])
    out = capsys.readouterr().out
    assert CB.diff in out  # the auto-approved second change was shown


def test_observe_only_adapter_is_skipped(tmp_path, fake_platform):
    _seed(tmp_path)
    applied = _run(tmp_path, fake_platform, {"fake": FakeObserveOnly()}, [])
    assert applied == []


def test_only_id_filters(tmp_path, fake_platform):
    _seed(tmp_path)
    fake = FakeMutating({"fake/a": [CA], "fake/b": [CB]})
    applied = _run(tmp_path, fake_platform, {"fake": fake}, ["y"], only_id="fake/a")
    assert fake.executed == [CA]
    assert [a.change.entry_id for a in applied] == ["fake/a"]


def test_apply_without_snapshot_errors(tmp_path, fake_platform):
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "r.yaml").write_text(REG)
    with pytest.raises(FileNotFoundError):
        _run(tmp_path, fake_platform, {"fake": FakeMutating({})}, [])


PHASED = (
    "entries:\n"
    "  - {id: fake/a, adapter: fake, domain: d, lifecycle: active, intent: i, phase: 5}\n"
    "  - {id: fake/b, adapter: fake, domain: d, lifecycle: active, intent: i, phase: 1}\n"
)

HUMAN = (
    "entries:\n"
    "  - {id: fake/a, adapter: fake, domain: d, lifecycle: active, intent: i, owner: human}\n"
)


def test_entries_apply_in_phase_order(tmp_path, fake_platform):
    _seed(tmp_path, PHASED)
    fake = FakeMutating({"fake/a": [CA], "fake/b": [CB]})
    _run(tmp_path, fake_platform, {"fake": fake}, ["a"])  # 'a' auto-approves the rest
    assert fake.executed == [CB, CA]  # phase 1 (b) converges before phase 5 (a)


def test_human_owned_entry_is_never_written(tmp_path, fake_platform):
    _seed(tmp_path, HUMAN)
    fake = FakeMutating({"fake/a": [CA]})
    applied = _run(tmp_path, fake_platform, {"fake": fake}, ["y"])
    assert fake.executed == []  # the plane never writes an owner:human entry
    assert applied == []


def test_execute_exception_is_contained(tmp_path, fake_platform):
    _seed(tmp_path)
    applied = _run(tmp_path, fake_platform, {"fake": FakeRaisingExecute()}, ["y"])
    assert len(applied) == 1
    assert applied[0].executed
    assert applied[0].result is not None and not applied[0].result.ok
    assert "execute raised" in applied[0].result.detail


def test_apply_writes_an_audit_record(tmp_path, fake_platform):
    _seed(tmp_path)
    fake = FakeMutating({"fake/a": [CA], "fake/b": [CB]})
    _run(tmp_path, fake_platform, {"fake": fake}, ["y", "n"])
    journal = tmp_path / "observed" / "testhost" / "applied.jsonl"
    assert journal.is_file()
    lines = [json.loads(line) for line in journal.read_text().splitlines()]
    assert {line["entry_id"]: line["executed"] for line in lines} == {
        "fake/a": True,
        "fake/b": False,
    }
    assert all("ts" in line and "actor" in line for line in lines)


def test_only_id_with_no_match_raises(tmp_path, fake_platform):
    # A typo'd --id must not fall through to "no changes" with exit 0; it must
    # be a loud error so the user knows the id, not the machine, is the problem.
    _seed(tmp_path)
    with pytest.raises(LookupError, match="fake/typo"):
        _run(
            tmp_path, fake_platform, {"fake": FakeMutating({})}, [], only_id="fake/typo"
        )


def test_journal_record_lands_before_the_next_change_runs(tmp_path, fake_platform):
    # Crash-safety: each record is appended as its change is decided, so a run
    # that dies mid-loop leaves the already-executed mutations on the record.
    # A confirm that raises on the second change simulates the mid-run death.
    _seed(tmp_path)
    fake = FakeMutating({"fake/a": [CA], "fake/b": [CB]})
    answers = iter(["y"])

    def confirm_then_crash(change):
        try:
            return next(answers)
        except StopIteration:
            raise RuntimeError("killed mid-run") from None

    with pytest.raises(RuntimeError, match="killed mid-run"):
        run_apply(
            tmp_path,
            platform=fake_platform(tmp_path),
            adapters={"fake": fake},
            confirm=confirm_then_crash,
            now=datetime(2026, 7, 22),
        )
    journal = tmp_path / "observed" / "testhost" / "applied.jsonl"
    lines = [json.loads(line) for line in journal.read_text().splitlines()]
    assert [(line["entry_id"], line["executed"], line["ok"]) for line in lines] == [
        ("fake/a", True, True)
    ]


def test_every_mutating_adapter_declares_its_converge_phase():
    # The documented order: packages(2) -> harness config(3) -> models(4) ->
    # secrets(5) -> services(6, load last against complete config). Encoded as
    # adapter data, so unphased entries converge in that order automatically.
    from planeops.core.contracts import can_apply
    from planeops.core.discovery import discover_adapters

    phases = {
        name: adapter.default_phase
        for name, adapter in discover_adapters().items()
        if can_apply(adapter)
    }
    assert phases == {
        "pkg-brew": 2,
        "pkg-npm": 2,
        "pkg-uv": 2,
        "chezmoi": 3,
        "ollama": 4,
        "secrets": 5,
        "launchd": 6,
        "systemd": 6,
    }


# ---- the interactive gate itself ----


def test_prompt_confirm_parses_answers(monkeypatch, capsys):
    from planeops.core.apply import prompt_confirm

    answers = iter(["y", "N", " a ", "", "yes"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert prompt_confirm(CA) == "y"
    assert prompt_confirm(CA) == "n"  # case-folded
    assert prompt_confirm(CA) == "a"  # whitespace stripped
    assert prompt_confirm(CA) == "n"  # empty answer never mutates
    assert prompt_confirm(CA) == "y"  # first letter decides
    assert "do a" in capsys.readouterr().out  # the diff is shown before asking


def test_prompt_confirm_defaults_to_no_without_stdin(monkeypatch):
    from planeops.core.apply import prompt_confirm

    def _eof(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)
    assert prompt_confirm(CA) == "n"  # non-interactive: never mutate


def test_a_crashing_plan_is_recorded_and_the_run_continues(tmp_path, fake_platform):
    # One adapter's broken plan must not abort the whole run; the failure is
    # journaled and the other entries still converge.
    class CrashyPlan:
        name = "fake"
        domains = ("d",)
        default_phase = 1

        def observe(self, ctx):
            return []

        def plan(self, entry, obs, ctx):
            if entry.id == "fake/a":
                raise RuntimeError("plan boom")
            return [CB]

        def execute(self, change, ctx):
            return Result(ok=True, detail="done")

    _seed(tmp_path)
    applied = _run(tmp_path, fake_platform, {"fake": CrashyPlan()}, ["y"])
    outcomes = {
        a.change.entry_id: (a.executed, a.result.ok if a.result else None)
        for a in applied
    }
    assert outcomes["fake/a"] == (False, False)  # recorded, not executed
    assert outcomes["fake/b"] == (True, True)  # the run continued
    journal = tmp_path / "observed" / "testhost" / "applied.jsonl"
    assert "plan boom" in journal.read_text()


def test_only_phase_filters(tmp_path, fake_platform):
    _seed(tmp_path, PHASED)  # fake/a phase 5, fake/b phase 1
    fake = FakeMutating({"fake/a": [CA], "fake/b": [CB]})
    applied = _run(tmp_path, fake_platform, {"fake": fake}, ["y"], only_phase=5)
    assert fake.executed == [CA]
    assert [a.change.entry_id for a in applied] == ["fake/a"]


def test_value_handle_goes_only_to_the_registered_secrets_adapter(
    tmp_path, fake_platform
):
    # A rogue adapter self-declaring the "secret" domain must NOT receive the
    # value-capable handle: the grant is pinned to the adapter registered under
    # the reserved name "secrets", not to a self-declared domain string.
    class RogueStore:
        name = "fake-store"

        def exists(self, name):
            return True

        def meta(self, name):
            return {"configured": True}

        def get(self, name):
            return "THE-VALUE"

    seen = {}

    class Rogue:
        name = "rogue"
        domains = ("secret",)
        default_phase = 1

        def observe(self, ctx):
            return []

        def plan(self, entry, obs, ctx=None):
            return (
                [Change("rogue/a", "configure", "d", {})]
                if entry.id == "rogue/a"
                else []
            )

        def execute(self, change, ctx):
            try:
                seen["value"] = ctx.secrets.get("anything")
            except Exception as exc:
                seen["value"] = exc
            return Result(ok=True, detail="d")

    reg = "entries:\n  - {id: rogue/a, adapter: rogue, domain: secret, lifecycle: active, intent: i}\n"
    _seed(tmp_path, reg=reg)
    _run(
        tmp_path,
        fake_platform,
        {"rogue": Rogue()},
        ["y"],
        secrets_store=RogueStore(),
    )
    # The rogue's execute got the PRESENCE-ONLY handle: get() raised.
    assert isinstance(seen["value"], Exception)
