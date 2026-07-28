from pathlib import Path

from engine.importers import Importer, discover_importers, render_proposal


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
    import yaml

    entries = [{"id": "secrets/x", "adapter": "secrets"}]
    assert yaml.safe_load(render_proposal(entries)) == {"entries": entries}
