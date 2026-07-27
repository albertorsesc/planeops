"""Apply loop: the engine owns confirmation. Exercised with a fake mutating
adapter and a scripted confirm, so nothing here touches the machine.
"""

import json
from datetime import datetime

import pytest

from engine.core.apply import run_apply
from engine.core.contracts import Change, Result

REG = (
    "entries:\n"
    "  - {id: fake/a, adapter: fake, domain: d, lifecycle: active, intent: i}\n"
    "  - {id: fake/b, adapter: fake, domain: d, lifecycle: active, intent: i}\n"
)


class FakeMutating:
    name = "fake"
    domains = ("d",)

    def __init__(self, changes_by_entry):
        self._changes = changes_by_entry
        self.executed = []

    def observe(self, ctx):
        return []

    def plan(self, entry, obs):
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

    def observe(self, ctx):
        return []

    def plan(self, entry, obs):
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


def test_all_in_domain_auto_approves_rest(tmp_path, fake_platform):
    _seed(tmp_path)
    fake = FakeMutating({"fake/a": [CA], "fake/b": [CB]})
    # Only one answer: 'a' on the first change auto-approves the rest of domain d.
    applied = _run(tmp_path, fake_platform, {"fake": fake}, ["a"])
    assert fake.executed == [CA, CB]
    assert all(a.executed for a in applied)


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
