"""The rich leaf: plain when captured, markup-proof, streams routed correctly."""

from planeops.providers import ui


def test_captured_output_is_plain_text(capsys):
    ui.good("all clear")
    ui.title("heading")
    out = capsys.readouterr().out
    assert "all clear" in out and "heading" in out
    assert "\x1b[" not in out  # no ANSI styling off-terminal


def test_observed_names_never_parse_as_markup(capsys):
    ui.line("[red]server[/red] literal [brackets]")
    assert "[red]server[/red] literal [brackets]" in capsys.readouterr().out


def test_err_and_note_land_on_stderr(capsys):
    ui.err("boom")
    ui.note("aside")
    ui.warn("careful", stderr=True)
    captured = capsys.readouterr()
    assert "boom" in captured.err and "aside" in captured.err
    assert "careful" in captured.err
    assert captured.out == ""


def test_table_renders_headers_and_rows_one_line_each(capsys):
    ui.table(["server", "clients"], [["alpha", "one, two"], ["beta", "(none)"]])
    out = capsys.readouterr().out
    assert "server" in out and "alpha" in out and "one, two" in out
    [alpha_line] = [ln for ln in out.splitlines() if "alpha" in ln]
    assert "one, two" in alpha_line  # row stays one line when captured
