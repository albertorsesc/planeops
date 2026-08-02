"""The importers package seam: discovery, shared rendering, and `--write`
landing proposals into registry/imported.yaml (merge + de-dupe by id).
"""

from pathlib import Path

import yaml

from planeops.importers import (
    Importer,
    discover_importers,
    render_proposal,
    write_proposal,
)


def test_discovers_the_built_in_importers():
    found = discover_importers()
    assert {"stackfile", "envfile"} <= set(found)


def test_every_discovered_importer_satisfies_the_contract():
    for kind, importer in discover_importers().items():
        assert isinstance(importer, Importer)
        assert importer.kind == kind
        # propose is pure and returns a list of entry dicts
        out = importer.propose("", None)
        assert isinstance(out, list)
        # note is a one-line header string
        assert isinstance(importer.note(Path("/x"), 0), str)


def test_render_proposal_is_shared_and_round_trips():
    entries = [{"id": "secrets/x", "adapter": "secrets"}]
    assert yaml.safe_load(render_proposal(entries)) == {"entries": entries}


# ---- write_proposal: land + merge + de-dupe ----


def _entries(*ids):
    return [
        {
            "id": i,
            "adapter": i.split("/")[0],
            "domain": "package",
            "lifecycle": "active",
            "tolerance": "report",
            "intent": "imported, verify",
        }
        for i in ids
    ]


def test_write_proposal_creates_then_merges_without_dupes(tmp_path):
    (tmp_path / "registry").mkdir()
    p, total = write_proposal(_entries("pkg-brew/a", "pkg-brew/b"), tmp_path)
    assert p == tmp_path / "registry" / "imported.yaml"
    ids = [e["id"] for e in yaml.safe_load(p.read_text())["entries"]]
    assert ids == ["pkg-brew/a", "pkg-brew/b"] and total == 2
    # a second write merges: keeps existing, adds new, de-dups the repeat
    _, total2 = write_proposal(_entries("pkg-brew/b", "pkg-brew/c"), tmp_path)
    ids = [e["id"] for e in yaml.safe_load(p.read_text())["entries"]]
    assert ids == ["pkg-brew/a", "pkg-brew/b", "pkg-brew/c"] and total2 == 3


def test_render_proposal_reads_like_a_document():
    # Registry files are documents humans edit: one blank line between entries,
    # not a dense machine dump.
    entries = [
        {"id": "a/one", "adapter": "a", "domain": "d", "lifecycle": "active",
         "intent": "i"},
        {"id": "a/two", "adapter": "a", "domain": "d", "lifecycle": "active",
         "intent": "i"},
    ]  # fmt: skip
    out = render_proposal(entries)
    assert (
        "\n\n- id: a/two" in out.replace("  - id", "- id") or "\n\n  - id: a/two" in out
    )
    assert yaml.safe_load(out) == {"entries": entries}


def test_write_proposal_appends_without_destroying_user_edits(tmp_path):
    # The file is prune-not-author: a user's comments and pruning marks must
    # survive a re-import. Only NEW entries are appended as text; the existing
    # file body is never re-dumped.
    (tmp_path / "registry").mkdir()
    target = tmp_path / "registry" / "imported.yaml"
    target.write_text(
        "entries:\n"
        "  # keep: verified 2026-08-02\n"
        "  - id: a/one\n"
        "    adapter: a\n"
        "    domain: d\n"
        "    lifecycle: active\n"
        "    intent: i\n"
    )
    new = [
        {"id": "a/one", "adapter": "a", "domain": "d", "lifecycle": "active",
         "intent": "i"},
        {"id": "a/two", "adapter": "a", "domain": "d", "lifecycle": "active",
         "intent": "i"},
    ]  # fmt: skip
    path, total = write_proposal(new, tmp_path)
    text = path.read_text()
    assert "# keep: verified 2026-08-02" in text  # the user's edit survived
    assert total == 2
    loaded = yaml.safe_load(text)
    assert [e["id"] for e in loaded["entries"]] == ["a/one", "a/two"]
