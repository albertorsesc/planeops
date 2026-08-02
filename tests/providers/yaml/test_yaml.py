"""The YAML port's contract. Asserts capabilities, never the vendor: these
tests must pass unchanged against any future provider."""

from planeops.providers import yaml


def test_load_and_dump_round_plain_data():
    data = {"entries": [{"id": "a/b", "phase": 3}]}
    assert yaml.load(yaml.dump(data)) == data


def test_load_all_reads_multi_document_streams():
    docs = yaml.load_all("a: 1\n---\nb: 2\n")
    assert docs == [{"a": 1}, {"b": 2}]


def test_malformed_input_raises_the_neutral_error():
    import pytest

    with pytest.raises(yaml.ParseError):
        yaml.load("a: [unclosed")


def test_edit_round_trip_preserves_comments_and_layout():
    # The capability the provider was chosen for: a human's comments and
    # blank lines survive load -> modify -> dump.
    text = (
        "# header comment\n"
        "entries:\n"
        "  # keep: verified by hand\n"
        "  - id: a/b\n"
        "    intent: original\n"
        "\n"
        "secrets:\n"
        "  store: sops\n"
    )
    doc = yaml.edit_load(text)
    doc["entries"].append({"id": "a/c", "intent": "added"})
    out = yaml.edit_dump(doc)
    assert "# header comment" in out
    assert "# keep: verified by hand" in out
    assert "id: a/c" in out
    reloaded = yaml.load(out)
    assert [e["id"] for e in reloaded["entries"]] == ["a/b", "a/c"]
    assert reloaded["secrets"] == {"store": "sops"}
