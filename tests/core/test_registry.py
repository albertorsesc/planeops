import pytest

from planeops.core.registry import load_registry
from planeops.core.schema import SchemaError


def _write(dirpath, name, text):
    (dirpath / name).write_text(text)


def test_loads_entries_and_globs_across_files(tmp_path):
    _write(
        tmp_path,
        "a.yaml",
        "entries:\n"
        "  - {id: manual/a, adapter: manual, domain: host, lifecycle: active, intent: i}\n",
    )
    _write(
        tmp_path,
        "unmanaged.yaml",
        "globs:\n  - {glob: '*/session-*', reason: ephemeral}\n",
    )
    reg = load_registry(tmp_path)
    assert [e.id for e in reg.entries] == ["manual/a"]
    assert reg.unmanaged[0].value == "*/session-*"
    assert reg.unmanaged[0].attested is False


def test_declared_adapters_and_host_filter(tmp_path):
    _write(
        tmp_path,
        "r.yaml",
        "entries:\n"
        "  - {id: manual/a, adapter: manual, domain: host, lifecycle: active, intent: i}\n"
        "  - {id: launchd/b, adapter: launchd, domain: service, lifecycle: active, intent: i, hosts: [other]}\n",
    )
    reg = load_registry(tmp_path)
    assert reg.declared_adapters() == {"manual", "launchd"}
    assert [e.id for e in reg.entries_for_host("thishost")] == ["manual/a"]


def test_duplicate_id_rejected(tmp_path):
    _write(
        tmp_path,
        "r.yaml",
        "entries:\n"
        "  - {id: manual/a, adapter: manual, domain: host, lifecycle: active, intent: i}\n"
        "  - {id: manual/a, adapter: manual, domain: host, lifecycle: parked, intent: j}\n",
    )
    with pytest.raises(SchemaError):
        load_registry(tmp_path)


def test_missing_dir_is_empty_registry(tmp_path):
    reg = load_registry(tmp_path / "nope")
    assert reg.entries == () and reg.unmanaged == ()


def test_publishers_load_as_attested_rules(tmp_path):
    _write(
        tmp_path,
        "unmanaged.yaml",
        "publishers:\n  - {publisher: ABCDE12345, reason: vendor updaters}\n",
    )
    reg = load_registry(tmp_path)
    assert [(r.value, r.attested) for r in reg.unmanaged] == [("ABCDE12345", True)]


def test_a_glob_and_a_publisher_can_share_one_file(tmp_path):
    _write(
        tmp_path,
        "unmanaged.yaml",
        "globs:\n  - {glob: '*/session-*', reason: ephemeral}\n"
        "publishers:\n  - {publisher: ABCDE12345, reason: vendor}\n",
    )
    reg = load_registry(tmp_path)
    assert sorted((r.value, r.attested) for r in reg.unmanaged) == [
        ("*/session-*", False),
        ("ABCDE12345", True),
    ]


def test_malformed_publisher_is_a_clean_schema_error(tmp_path):
    _write(tmp_path, "unmanaged.yaml", "publishers:\n  - just-a-string\n")
    with pytest.raises(SchemaError):
        load_registry(tmp_path)


def test_malformed_glob_is_a_clean_schema_error(tmp_path):
    # A plain string under `globs:` (not a `{glob: ...}` mapping) must raise a
    # SchemaError like a bad entry does, not a raw TypeError on `raw["glob"]`.
    _write(tmp_path, "unmanaged.yaml", "globs:\n  - just-a-string\n")
    with pytest.raises(SchemaError):
        load_registry(tmp_path)


def test_unknown_top_level_key_is_rejected_with_a_suggestion(tmp_path):
    # `entrys:` must not make the whole file silently contribute nothing.
    (tmp_path / "r.yaml").write_text(
        "entrys:\n  - {id: a/b, adapter: a, domain: d, lifecycle: active, intent: i}\n"
    )
    with pytest.raises(SchemaError, match="entries"):
        load_registry(tmp_path)


def test_glob_value_must_be_a_string(tmp_path):
    (tmp_path / "u.yaml").write_text("globs:\n  - {glob: 3, reason: r}\n")
    with pytest.raises(SchemaError, match="glob"):
        load_registry(tmp_path)


def test_a_non_registry_file_in_registry_names_the_allowed_keys(tmp_path):
    # A file that isn't a registry document at all (e.g. an encrypted secrets
    # store parked here by mistake; its default home is the instance root) has
    # no near-miss key, so the error lists what registry/ files may contain.
    (tmp_path / "secrets.sops.yaml").write_text(
        "test-canary: ENC[data]\nsops:\n  version: '3'\n"
    )
    with pytest.raises(SchemaError, match="expected one of: entries, globs"):
        load_registry(tmp_path)
