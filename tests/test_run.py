"""The shared subprocess seam: real commands, real timeouts, distinct failures.

These run actual processes (echo, sleep, a nonexistent binary), so the seam's
contract is proven against the OS, not a fake: output capture, the not-found
code, the timeout code, and that a timeout reads differently from a missing
command (an operator must be able to tell "tool absent" from "tool still
running").
"""

from engine._run import default_run


def test_captures_output_and_exit_code():
    res = default_run(["echo", "hi"])
    assert res.code == 0 and res.out.strip() == "hi" and res.err == ""


def test_command_not_found_is_127():
    res = default_run(["definitely-not-a-real-binary-xyz"])
    assert res.code == 127
    assert "timed out" not in res.err


def test_timeout_is_124_and_says_the_command_may_still_run():
    # 124 is the GNU-timeout convention; the detail must warn that the child
    # (or its grandchildren) may still be mutating the machine.
    res = default_run(["sleep", "5"], timeout=0.1)
    assert res.code == 124
    assert "timed out" in res.err and "still be running" in res.err


def test_timeout_none_means_no_ceiling():
    # Execute paths for long converge ops (brew install, ollama pull) pass
    # None: the human just confirmed the change and owns the wait.
    res = default_run(["sleep", "0.2"], timeout=None)
    assert res.code == 0


def test_default_timeout_still_applies_when_omitted():
    res = default_run(["echo", "ok"])  # no timeout arg: observe-path shape
    assert res.code == 0
