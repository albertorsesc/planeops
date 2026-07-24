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


def _scripted(answers):
    it = iter(answers)
    return lambda change: next(it)


def _seed(tmp_path):
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "r.yaml").write_text(REG)
    obs = tmp_path / "observed" / "testhost"
    obs.mkdir(parents=True)
    (obs / "snapshot.json").write_text(
        json.dumps({"host": "testhost", "ts": "t", "engine_version": "0", "observed": [], "uncovered": []})
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
    assert [(a.change.entry_id, a.executed) for a in applied] == [("fake/a", True), ("fake/b", False)]


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
