"""The importers package seam: discovery, shared rendering, and `--write`
landing proposals into registry/imported.yaml (merge + de-dupe by id).
"""

from pathlib import Path

import yaml

from engine.importers import (
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
