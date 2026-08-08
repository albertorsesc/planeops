"""The presentation port: semantic surface only, drawing details live in the leaf."""

from planeops.providers import ui


def test_port_exposes_the_semantic_surface():
    for name in ui.__all__:
        assert callable(getattr(ui, name))
    assert set(ui.__all__) == {
        "bad", "breakdown", "err", "good", "headline", "help_formatter",
        "hint", "item", "line", "note", "panel", "section", "table",
        "title", "warn",
    }  # fmt: skip
