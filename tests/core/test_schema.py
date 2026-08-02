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
            [{"ref": "secret://openrouter", "injected_as": "file:~/.env#KEY"}]
        )
    )
    assert e.secrets[0]["ref"] == "secret://openrouter"


def test_secret_ref_must_be_a_mapping():
    with pytest.raises(SchemaError, match="secrets"):
        entry_from_dict(_secret_entry(["secret://x"]))


def test_secret_ref_must_carry_a_secret_uri():
    with pytest.raises(SchemaError, match="secret://"):
        entry_from_dict(_secret_entry([{"ref": "sops/x"}]))


def test_secret_injected_as_shape_is_checked():
    with pytest.raises(SchemaError, match="injected_as"):
        entry_from_dict(_secret_entry([{"ref": "secret://x", "injected_as": 42}]))


def test_env_injection_is_rejected_as_unsupported():
    # The old error message advertised env:NAME as a valid form while
    # materialization silently dropped it: a user following the tool's own
    # words got a no-op. Unsupported must say so at load.
    with pytest.raises(SchemaError, match="not supported"):
        entry_from_dict(
            _secret_entry([{"ref": "secret://x", "injected_as": "env:KEY"}])
        )


def test_injected_as_must_be_a_file_target_with_a_key():
    for bad in ("file:~/.env", "file:#KEY", "file:~/.env#", "somewhere"):
        with pytest.raises(SchemaError, match=r"file:<path>#KEY"):
            entry_from_dict(_secret_entry([{"ref": "secret://x", "injected_as": bad}]))


def test_unknown_key_in_a_secrets_item_is_rejected():
    # `injectd_as:` used to be silently dropped -> the secret was declared but
    # never materialized anywhere.
    with pytest.raises(SchemaError, match="injected_as"):
        entry_from_dict(
            _secret_entry([{"ref": "secret://x", "injectd_as": "file:~/.e#K"}])
        )


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


# ---- typo'd KEYS are rejected, not silently ignored ----


def test_unknown_entry_key_is_rejected_with_a_suggestion():
    # `tolerence: alert` used to be silently dropped -> tolerance defaulted to
    # report and the escalation the user wrote never happened.
    with pytest.raises(SchemaError, match="tolerance"):
        entry_from_dict(
            {"id": "a/b", "adapter": "a", "domain": "d", "lifecycle": "active",
             "intent": "i", "tolerence": "alert"}
        )  # fmt: skip


def test_unknown_entry_key_without_a_close_match_lists_the_allowed_set():
    # No suggestion possible -> the error names what WOULD be valid, so a file
    # that plain doesn't belong here explains itself.
    with pytest.raises(SchemaError, match="banana.*expected one of.*adapter"):
        entry_from_dict(
            {"id": "a/b", "adapter": "a", "domain": "d", "lifecycle": "active",
             "intent": "i", "banana": 1}
        )  # fmt: skip


def test_needs_typo_is_caught():
    # `need:` silently meant "no dependency tracking".
    with pytest.raises(SchemaError, match="needs"):
        entry_from_dict(
            {"id": "a/b", "adapter": "a", "domain": "d", "lifecycle": "active",
             "intent": "i", "need": ["x/y"]}
        )  # fmt: skip


def test_string_fields_must_be_strings():
    with pytest.raises(SchemaError, match="intent"):
        entry_from_dict(
            {"id": "a/b", "adapter": "a", "domain": "d", "lifecycle": "active",
             "intent": 123}
        )  # fmt: skip


def test_hosts_items_must_be_strings():
    # A numeric host never matches a hostname: the entry would silently never
    # apply anywhere.
    with pytest.raises(SchemaError, match="hosts"):
        entry_from_dict(
            {"id": "a/b", "adapter": "a", "domain": "d", "lifecycle": "active",
             "intent": "i", "hosts": [1]}
        )  # fmt: skip


def test_adapter_name_charset_is_enforced_on_entries():
    # `adapter` feeds `<adapter>/<native_id>` keys split at the FIRST slash;
    # a slash in the adapter name makes keys unrecoverably ambiguous.
    with pytest.raises(SchemaError, match="adapter"):
        entry_from_dict(
            {"id": "x/y", "adapter": "bad/name", "domain": "d",
             "lifecycle": "active", "intent": "i"}
        )  # fmt: skip


def test_secret_ref_is_a_single_name_segment():
    # The store is instance configuration, never part of the ref: swapping
    # stores must touch zero entries.
    e = entry_from_dict(_secret_entry([{"ref": "secret://openrouter-api-key"}]))
    assert e.secrets[0]["ref"] == "secret://openrouter-api-key"


def test_secret_ref_with_a_store_segment_is_rejected_with_the_migration_hint():
    # The old two-segment form bound a store kind into every entry; the
    # segment was validated in the error text and then DISCARDED by the only
    # consumer. Rejected loudly with the fix spelled out.
    with pytest.raises(SchemaError, match="instance.yaml"):
        entry_from_dict(
            _secret_entry([{"ref": "secret://sops/openrouter", "injected_as": None}])
        )


def test_secret_ref_name_charset(tmp_path):
    for bad in ("secret://", "secret://a b", "secret://a/b/c"):
        with pytest.raises(SchemaError):
            entry_from_dict(_secret_entry([{"ref": bad}]))


def test_logs_field_is_a_tuple_of_paths():
    # An entry records where its asset logs, so the manifest answers "where do
    # I look when this misbehaves" without hunting.
    e = entry_from_dict(
        {"id": "a/b", "adapter": "a", "domain": "d", "lifecycle": "active",
         "intent": "i", "logs": ["~/Library/Logs/x/out.log", "journalctl --user -u x"]}
    )  # fmt: skip
    assert e.logs == ("~/Library/Logs/x/out.log", "journalctl --user -u x")


def test_logs_items_must_be_non_empty_strings():
    for bad in ([3], [""], "not-a-list"):
        with pytest.raises(SchemaError, match="logs"):
            entry_from_dict(
                {"id": "a/b", "adapter": "a", "domain": "d",
                 "lifecycle": "active", "intent": "i", "logs": bad}
            )  # fmt: skip
