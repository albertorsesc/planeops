from planeops.cli._text import n_entries


def test_singular_and_plural():
    assert n_entries(1) == "1 entry"
    assert n_entries(0) == "0 entries"
    assert n_entries(73) == "73 entries"
