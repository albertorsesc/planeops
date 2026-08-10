"""The one module that knows `rich` exists.

Styling is selective: a line's HEAD (the part carrying the verdict) takes the
semantic color, its DETAIL (paths, timestamps) prints dim, and everything else
stays the terminal's default. Both consoles disable markup and highlighting:
observed names (a server called `[red]`, a path with brackets) must print
literally, never parse as styling. Rich handles the rest of the contract:
plain text when the stream is not a terminal, and the NO_COLOR convention.
Piped output gets a wide virtual console so a long row stays one greppable
line instead of folding at a terminal width no terminal is using.
"""

from __future__ import annotations

import sys
from typing import IO

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

_THEME = Theme(
    {
        "title": "bold",
        "good": "green",
        "warn": "yellow",
        "bad": "red",
        "note": "dim",
    }
)


def _console(stream: IO[str]) -> Console:
    return Console(
        theme=_THEME,
        markup=False,
        highlight=False,
        soft_wrap=True,
        stderr=stream is sys.stderr,
        width=None if stream.isatty() else 400,
    )


_out = _console(sys.stdout)
_err = _console(sys.stderr)


def _emit(console: Console, style: str | None, text: str, detail: str | None) -> None:
    out = Text()
    out.append(text, style=style)
    if detail:
        out.append(f" {detail}", style="note")
    console.print(out)


def line(text: str = "", detail: str | None = None) -> None:
    """A plain line on stdout; `detail` (a path, a timestamp) prints dim."""
    _emit(_out, None, text, detail)


def title(text: str, detail: str | None = None) -> None:
    """A section heading."""
    _emit(_out, "title", text, detail)


def good(text: str, detail: str | None = None) -> None:
    """A success line: the head is green, the detail dim."""
    _emit(_out, "good", text, detail)


def warn(text: str, detail: str | None = None, *, stderr: bool = False) -> None:
    """A caution line: part of a report or an advisory, not a failure."""
    _emit(_err if stderr else _out, "warn", text, detail)


def bad(text: str, detail: str | None = None) -> None:
    """A failure line inside a report on stdout (the report itself succeeded)."""
    _emit(_out, "bad", text, detail)


def err(text: str) -> None:
    """An error line on stderr."""
    _err.print(text, style="bad")


def note(text: str) -> None:
    """An advisory line on stderr (declines, hints); dim, never alarming."""
    _err.print(text, style="note")


# Domain states, not color names: the CLI speaks triage, only this leaf
# speaks yellow. Symbols carry state on their own, so color is never
# load-bearing (NO_COLOR, monochrome terminals, color-blind readers).
_SYMBOL = {"ok": "✓", "alert": "✗", "report": "!", "unknown": "~", "neutral": "·"}
_STATE_STYLE = {
    "ok": "good",
    "alert": "bad",
    "report": "warn",
    "unknown": "warn",
    "neutral": "note",
}


def headline(state: str, text: str, detail: str | None = None) -> None:
    """The one-glance answer: a state symbol, the answer in bold, provenance
    dim. `state` is ok / alert / report / plain."""
    out = Text()
    if state != "plain":
        out.append(_SYMBOL[state] + " ", style=_STATE_STYLE[state])
    out.append(text, style="title")
    if detail:
        out.append(f" {detail}", style="note")
    _out.print(out)


def section(name: str, count: int) -> None:
    """A blank line, then a bold `name (count)` header. Callers skip empty
    sections entirely: absence is the good news, not a zero."""
    _out.print()
    _out.print(f"{name} ({count})", style="title")


def item(state: str, ident: str, message: str, ident_width: int) -> None:
    """One triaged item: symbol, aligned identifier (its `adapter/` prefix
    dim so the eye lands on the meaningful segment), then the message."""
    out = Text("  ")
    out.append(_SYMBOL[state] + " ", style=_STATE_STYLE[state])
    prefix, sep, rest = ident.partition("/")
    if sep:
        out.append(prefix + "/", style="note")
        out.append(rest)
    else:
        out.append(ident)
    out.append(" " * max(ident_width - len(ident), 0))
    if message:
        out.append("  " + message)
    _out.print(out)


def group(label: str, detail: str = "") -> None:
    """A group header inside a section: what its items have in common (their
    adapter, and the one message they all carry), stated once so the list
    below can be bare names."""
    out = Text("  ")
    out.append(label, style="title")
    if detail:
        out.append(" · ", style="note")
        out.append(detail, style="note")
    _out.print(out)


# Packing width: a real terminal's own width, but bounded on a pipe (where the
# console is deliberately wide) so a packed block stays readable either way.
_PACK_WIDTH = 100


def _pack_widths(names: list[str], columns: int, width: int) -> list[int] | None:
    """Per-column widths for a row-major grid, or None when it does not fit.
    Columns are sized to their own longest entry, so one long name costs its
    column only, not every column."""
    widths = []
    for c in range(columns):
        cells = names[c::columns]  # row-major fill: column c holds every cth name
        widths.append(max(len(n) for n in cells) + 4)  # symbol, space, padding
    return widths if sum(widths) <= width else None


def packed(state: str, names: list[str]) -> None:
    """Bare identifiers under a group, packed into aligned columns. A long
    list of short names is a shape to scan, not a column to read. The layout
    is computed here rather than delegated, so the same input always packs
    the same way."""
    if not names:
        return
    width = min(_out.width, _PACK_WIDTH) - 4  # the block's own indent
    columns, widths = 1, [max(len(n) for n in names) + 4]
    for candidate in range(min(len(names), 8), 1, -1):
        fit = _pack_widths(names, candidate, width)
        if fit is not None:
            columns, widths = candidate, fit
            break
    for start in range(0, len(names), columns):
        row = names[start : start + columns]
        out = Text("    ")
        for col, name in enumerate(row):
            out.append(_SYMBOL[state] + " ", style=_STATE_STYLE[state])
            out.append(name.ljust(widths[col] - 2))
        _out.print(Text(out.plain.rstrip(), spans=out.spans))


def hint(text: str) -> None:
    """A dim indented footnote under a section (shared guidance, truncation
    notes, navigation) on stdout."""
    _out.print(Text("  " + text, style="note"))


def breakdown(pairs: list[tuple[str, int]]) -> None:
    """One dim line of `name count` pairs, dot-separated: the compact
    composition summary under a headline."""
    _out.print(Text("  " + " · ".join(f"{k} {v}" for k, v in pairs), style="note"))


def panel(title: str, body: str) -> None:
    """The one framed element in the tool: the about-to-change moment. The
    frame separates content under review from surrounding chatter."""
    from rich.panel import Panel

    _out.print(
        Panel(
            body,
            title=title,
            title_align="left",
            border_style="note",
            expand=False,
            padding=(0, 1),
        )
    )


def help_formatter() -> type:
    """The argparse formatter class that styles every --help page; vendor
    code stays behind this seam like all drawing does."""
    from rich_argparse import RichHelpFormatter

    return RichHelpFormatter


def table(
    headers: list[str], rows: list[list[str]], styles: list[str | None] | None = None
) -> None:
    """A bordered table. A cell may hold newlines (one fact per line); when
    any row does, separator lines appear between rows so a multi-line row
    reads as one unit. `styles` names a semantic style per column (good /
    warn / note), never a color."""
    from rich import box

    multiline = any("\n" in cell for row in rows for cell in row)
    t = Table(
        box=box.ROUNDED,
        header_style="title",
        border_style="note",
        show_lines=multiline,
        padding=(0, 1),
    )
    for i, h in enumerate(headers):
        style = styles[i] if styles and i < len(styles) else None
        t.add_column(h, overflow="fold", style=style)
    for row in rows:
        t.add_row(*row)
    _out.print(t)
