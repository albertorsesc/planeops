"""Terminal presentation port: every human-facing line the CLI prints goes
through these functions, and only the leaf module knows which drawing library
draws them (`rich` today). Swapping or removing the library is a one-leaf
change; an architecture fitness test fails any import of it elsewhere.

The port is deliberately small and semantic: commands say WHAT a line is
(a title, a success, a warning, an error), never how to color it. Styling
appears only on a real terminal: piped or captured output is plain text, the
NO_COLOR convention is respected, and `--json` outputs never pass through
here at all.
"""

from planeops.providers.ui.rich import (
    bad,
    breakdown,
    err,
    good,
    group,
    headline,
    help_formatter,
    hint,
    item,
    line,
    note,
    packed,
    panel,
    section,
    table,
    title,
    warn,
)

__all__ = [
    "bad",
    "breakdown",
    "err",
    "good",
    "group",
    "headline",
    "help_formatter",
    "hint",
    "item",
    "line",
    "note",
    "packed",
    "panel",
    "section",
    "table",
    "title",
    "warn",
]
