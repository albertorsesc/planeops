import pytest

from planeops.core.schema import (
    Auth,
    Entry,
    Klass,
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
    ok = entry_from_dict(
        _raw(**{"class": "data", "data": {"location": "~/x", "sync": "git"}})
    )
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


def test_needs_defaults_empty_and_parses_a_list():
    assert entry_from_dict(_raw()).needs == ()
    e = entry_from_dict(_raw(needs=["ollama/emb", "pkg-brew/gh"]))
    assert e.needs == ("ollama/emb", "pkg-brew/gh")


@pytest.mark.parametrize("bad", ["ollama/emb", [1, 2], [""], [None]])
def test_needs_must_be_a_list_of_nonempty_strings(bad):
    with pytest.raises(SchemaError):
        entry_from_dict(_raw(needs=bad))


def test_non_scalar_enum_value_is_a_clean_schema_error():
    # A YAML list where a scalar enum is expected (e.g. `lifecycle: [active]` from a
    # stray `-`) must be a SchemaError, not a raw TypeError from the enum lookup.
    with pytest.raises(SchemaError):
        entry_from_dict(_raw(lifecycle=["active"]))


def test_non_string_scope_is_a_clean_schema_error():
    # `scope: 123` must not reach `.startswith` and raise AttributeError.
    with pytest.raises(SchemaError):
        entry_from_dict(_raw(scope=123))


# ---- secrets refs are validated, not accepted as any dict ----


def _secret_entry(secrets):
    return {
        "id": "svc/x",
        "adapter": "svc",
        "domain": "service",
        "lifecycle": "active",
        "intent": "i",
        "secrets": secrets,
    }


def test_valid_secret_ref_passes():
    e = entry_from_dict(
        _secret_entry(
            [{"ref": "secret://sops/openrouter", "injected_as": "file:~/.env#KEY"}]
        )
    )
    assert e.secrets[0]["ref"] == "secret://sops/openrouter"


def test_secret_ref_must_be_a_mapping():
    with pytest.raises(SchemaError, match="secrets"):
        entry_from_dict(_secret_entry(["secret://sops/x"]))


def test_secret_ref_must_carry_a_secret_uri():
    with pytest.raises(SchemaError, match="secret://"):
        entry_from_dict(_secret_entry([{"ref": "sops/x"}]))


def test_secret_injected_as_shape_is_checked():
    with pytest.raises(SchemaError, match="injected_as"):
        entry_from_dict(_secret_entry([{"ref": "secret://sops/x", "injected_as": 42}]))


# ---- scalar fields are type-checked, not passed through ----


def test_phase_must_be_an_integer():
    # YAML `phase: "3"` used to load fine and then crash apply's phase sort
    # with a TypeError; the schema now rejects it at load with the entry named.
    with pytest.raises(SchemaError, match="phase"):
        entry_from_dict(
            {"id": "a/b", "adapter": "a", "domain": "d", "lifecycle": "active",
             "intent": "i", "phase": "3"}
        )  # fmt: skip


def test_phase_rejects_bool():
    # bool is an int subclass; `phase: true` is a typo, not phase 1.
    with pytest.raises(SchemaError, match="phase"):
        entry_from_dict(
            {"id": "a/b", "adapter": "a", "domain": "d", "lifecycle": "active",
             "intent": "i", "phase": True}
        )  # fmt: skip


def test_pin_must_be_a_string():
    # YAML `pin: 1.2` parses as a float; version comparison then misbehaves.
    with pytest.raises(SchemaError, match="pin"):
        entry_from_dict(
            {"id": "a/b", "adapter": "a", "domain": "d", "lifecycle": "active",
             "intent": "i", "pin": 1.2}
        )  # fmt: skip
