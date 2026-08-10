"""The presentation port: semantic surface only, drawing details live in the leaf."""

from planeops.providers import ui


def test_port_exposes_the_semantic_surface():
    for name in ui.__all__:
        assert callable(getattr(ui, name))
    assert set(ui.__all__) == {
        "bad", "breakdown", "err", "good", "group", "headline",
        "help_formatter", "hint", "item", "line", "note", "packed", "panel",
        "section", "table", "title", "warn",
    }  # fmt: skip


# ---- packed: a long list of short names is a shape, not a column ----


def test_packed_puts_several_names_on_a_row(capsys):
    ui.packed("unknown", [f"tool{i}" for i in range(12)])
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) < 12  # packed, not one per line
    assert all(ln.startswith("    ") for ln in lines)  # indented under its group
    printed = " ".join(lines)
    for i in range(12):
        assert f"tool{i}" in printed  # nothing dropped by the packing


def test_packed_columns_are_sized_independently(capsys):
    # One long name must cost its own column only. With row-major fill and two
    # columns, the long name and the short ones live in different columns.
    ui.packed("unknown", ["a-very-long-name-that-dominates", "b", "c", "d"])
    out = capsys.readouterr().out
    short_row = [ln for ln in out.splitlines() if "b" in ln][0]
    assert len(short_row) < 60  # the short column did not inherit the long width


def test_packed_is_deterministic(capsys):
    names = ["alpha", "beta", "gamma", "delta", "epsilon"]
    ui.packed("alert", names)
    first = capsys.readouterr().out
    ui.packed("alert", names)
    assert capsys.readouterr().out == first


def test_packed_rows_carry_no_trailing_whitespace(capsys):
    ui.packed("unknown", ["one", "two", "three"])
    for line in capsys.readouterr().out.splitlines():
        assert line == line.rstrip()


def test_packed_nothing_prints_nothing(capsys):
    ui.packed("unknown", [])
    assert capsys.readouterr().out == ""


def test_group_states_what_the_rows_share(capsys):
    ui.group("footprint", "observed but not in the registry")
    out = capsys.readouterr().out
    assert "footprint" in out and "observed but not in the registry" in out


def test_group_without_a_detail_is_just_the_label(capsys):
    ui.group("launchd")
    assert capsys.readouterr().out.strip() == "launchd"
