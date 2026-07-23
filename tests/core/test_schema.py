import pytest

from engine.core.schema import (
    Auth,
    Entry,
    Klass,
    Lifecycle,
    Owner,
    SchemaError,
    Tolerance,
    entry_from_dict,
)


def _raw(**over):
    base = {
        "id": "manual/thing",
        "adapter": "manual",
        "domain": "host",
        "lifecycle": "active",
        "intent": "why it exists",
    }
    base.update(over)
    return base


def test_minimal_entry_applies_defaults():
    e = entry_from_dict(_raw())
    assert isinstance(e, Entry)
    assert e.klass is Klass.recipe
    assert e.scope == "machine"
    assert e.hosts == ("any",)
    assert e.owner is Owner.runtime
    assert e.tolerance is Tolerance.report
    assert e.auth is Auth.none


def test_native_id_strips_adapter_prefix():
    assert entry_from_dict(_raw(id="ollama/qwen3:30b")).native_id == "qwen3:30b"
    assert entry_from_dict(_raw(id="bareid")).native_id == "bareid"


@pytest.mark.parametrize("field", ["id", "adapter", "domain", "lifecycle", "intent"])
def test_missing_required_field_raises(field):
    raw = _raw()
    del raw[field]
    with pytest.raises(SchemaError):
        entry_from_dict(raw)


def test_bad_lifecycle_names_the_entry_and_allowed_values():
    with pytest.raises(SchemaError) as exc:
        entry_from_dict(_raw(lifecycle="zombie"))
    msg = str(exc.value)
    assert "manual/thing" in msg and "active" in msg


def test_data_class_requires_data_block():
    with pytest.raises(SchemaError):
        entry_from_dict(_raw(**{"class": "data"}))
    ok = entry_from_dict(_raw(**{"class": "data", "data": {"location": "~/x", "sync": "git"}}))
    assert ok.klass is Klass.data


def test_project_scope_prefix_accepted():
    e = entry_from_dict(_raw(scope="project:/abs/path"))
    assert e.scope == "project:/abs/path"


def test_bad_scope_rejected():
    with pytest.raises(SchemaError):
        entry_from_dict(_raw(scope="somewhere"))


def test_applies_to_host():
    pinned = entry_from_dict(_raw(hosts=["laptop"]))
    assert pinned.applies_to_host("laptop")
    assert not pinned.applies_to_host("server")
    assert entry_from_dict(_raw()).applies_to_host("anything")
