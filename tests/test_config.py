from planeops.config import load_instance, section


def test_no_root_is_empty():
    assert load_instance(None) == {}
    assert section(None, "mcp") == {}


def test_missing_file_is_empty(tmp_path):
    assert load_instance(tmp_path) == {}
    assert section(tmp_path, "mcp") == {}


def test_malformed_yaml_is_empty(tmp_path):
    (tmp_path / "instance.yaml").write_text("mcp: [unterminated\n")
    assert load_instance(tmp_path) == {}


def test_non_mapping_document_is_empty(tmp_path):
    (tmp_path / "instance.yaml").write_text("- just\n- a\n- list\n")
    assert load_instance(tmp_path) == {}


def test_reads_sections(tmp_path):
    (tmp_path / "instance.yaml").write_text(
        "mcp:\n  sources: []\nsecrets:\n  store: secrets.sops.yaml\n"
    )
    assert section(tmp_path, "secrets") == {"store": "secrets.sops.yaml"}
    assert section(tmp_path, "mcp") == {"sources": []}


def test_absent_or_scalar_section_is_empty_mapping(tmp_path):
    (tmp_path / "instance.yaml").write_text("mcp: not-a-mapping\n")
    assert section(tmp_path, "mcp") == {}
    assert section(tmp_path, "importer") == {}
