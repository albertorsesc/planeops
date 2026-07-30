import pytest

from engine.core.registry import load_registry
from engine.core.schema import SchemaError


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
    assert reg.unmanaged[0].glob == "*/session-*"


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


def test_malformed_glob_is_a_clean_schema_error(tmp_path):
    # A plain string under `globs:` (not a `{glob: ...}` mapping) must raise a
    # SchemaError like a bad entry does, not a raw TypeError on `raw["glob"]`.
    _write(tmp_path, "unmanaged.yaml", "globs:\n  - just-a-string\n")
    with pytest.raises(SchemaError):
        load_registry(tmp_path)
