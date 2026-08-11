"""Asking a human, and knowing when there is none.

Every verb that can change something asks first, and every one of them needs
the same two answers: what the human said, or that there is no human. This is
that one place, so the nine prompts in the CLI cannot drift into nine
different ideas of what "nobody answered" means.

`None` means nobody: stdin reached EOF, or is detached, or was closed at the
file-descriptor level, which Python reports three different ways and one of
which is not an exception a caller would think to catch. Each of those
arrives here as `None`, and every caller turns `None` into its conservative
branch: decline the change, skip the seeding, refuse to guess a path.

Deliberately NOT a terminal check. Answers piped in are answers: a script
that writes `y` has decided, and `plane apply` has no flag that would replace
it. A terminal check would make the tool deaf to that, so an open stdin that
never delivers a line blocks, exactly as any program reading stdin does. A
caller with nobody to ask says so by closing it (`plane init . </dev/null`).
"""

from __future__ import annotations


def ask(question: str) -> str | None:
    """The human's answer, or None when there is nobody to ask.

    The answer is returned verbatim; interpreting it (trimming, defaulting an
    empty line) belongs to the caller, because what Enter means differs
    between a `(y/N)` and a "path or Enter to accept"."""
    try:
        return input(question)
    except (EOFError, OSError, ValueError):
        # EOF: stdin ended. OSError: no such device, a detached process.
        # ValueError: reading a closed file object.
        return None
    except RuntimeError as exc:
        # "lost sys.stdin" when the descriptor itself is gone. Only that one:
        # any other RuntimeError is a real bug and must surface.
        if "stdin" in str(exc):
            return None
        raise
