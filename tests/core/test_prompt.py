"""Asking a human, and knowing when there is none.

The contract every verb depends on: an answer comes back when one is
available, from a terminal or from a pipe, and `None` comes back when there
is nobody to ask. `None` is what makes each caller take its conservative
branch, so the ways stdin can be missing all have to arrive there rather
than as a traceback.
"""

import builtins
import io
import sys

import pytest

from planeops.core.prompt import ask


def test_an_answer_is_returned_verbatim(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda prompt="": "  Yes  ")
    assert ask("q? ") == "  Yes  "  # trimming is the caller's business


def test_a_piped_answer_is_read(monkeypatch):
    # Piping is how a script answers, and `plane apply` has no flag for it, so
    # this must keep working: a terminal check here would make the tool deaf.
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))
    monkeypatch.setattr(
        builtins, "input", lambda prompt="": sys.stdin.readline().rstrip("\n")
    )
    assert ask("q? ") == "y"


def test_an_empty_line_is_an_answer_not_an_absence(monkeypatch):
    # Enter means "accept the default", which is different from having nobody
    # to ask; callers distinguish "" from None.
    monkeypatch.setattr(builtins, "input", lambda prompt="": "")
    assert ask("q? ") == ""


@pytest.mark.parametrize(
    "failure",
    [
        EOFError("end of input"),
        OSError("no such device or address"),
        RuntimeError("lost sys.stdin"),
        ValueError("I/O operation on closed file"),
    ],
)
def test_every_way_stdin_can_be_missing_answers_none(monkeypatch, failure):
    # A closed stdin raises EOFError, a detached one OSError, and an
    # fd-level-closed one RuntimeError("lost sys.stdin"). All three mean the
    # same thing to a caller, and none of them should reach the user as a
    # traceback while a mutation is pending.
    def boom(prompt=""):
        raise failure

    monkeypatch.setattr(builtins, "input", boom)
    assert ask("q? ") is None


def test_an_unrelated_error_is_not_swallowed(monkeypatch):
    # Only "nobody to ask" is absorbed; a real bug must still surface.
    def boom(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr(builtins, "input", boom)
    with pytest.raises(KeyboardInterrupt):
        ask("q? ")


def test_the_prompt_text_reaches_input(monkeypatch):
    seen = {}

    def capture(prompt=""):
        seen["prompt"] = prompt
        return "y"

    monkeypatch.setattr(builtins, "input", capture)
    ask("proceed? (y/N) ")
    assert seen["prompt"] == "proceed? (y/N) "
