"""The release guard: a version bump and its notes must tell one story.

The rule under test is CONTRIBUTING's: one slot means "a contract moved" (the
minor while 0.x, the major from 1.0), everything else is a patch. These cases
include the drift this guard exists to prevent, which nine real releases went
through unnoticed.
"""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "check_version_bump",
    Path(__file__).resolve().parent.parent / "scripts/check_version_bump.py",
)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)  # type: ignore[union-attr]

FEATURE = "### Added\n\n- a new adapter\n"
FIX = "### Fixed\n\n- a wrong branch\n"
BREAK = "### Changed\n\n- **BREAKING:** the registry schema moved\n"


# ---- which slot a bump moves ----


@pytest.mark.parametrize(
    "previous,current,expected",
    [
        ("0.10.0", "0.10.1", "other"),  # pre-1.0 patch
        ("0.10.0", "0.11.0", "contract"),  # pre-1.0 the minor is the contract
        ("0.10.1", "1.0.0", "contract"),  # crossing to 1.0
        ("1.0.0", "1.1.0", "other"),  # post-1.0 the minor is features
        ("1.0.0", "2.0.0", "contract"),  # post-1.0 the major is the contract
        ("1.0.0", "1.0.1", "other"),
        ("0.10.0", "0.10.0", "none"),
        ("0.11.0", "0.10.0", "backwards"),
    ],
)
def test_moved_slot(previous, current, expected):
    assert guard.moved_slot(previous, current) == expected


# ---- the agreement the guard enforces ----


def test_a_feature_takes_the_patch_slot_pre_1_0():
    assert guard.check("0.10.0", "0.10.1", FEATURE) == []


def test_the_drift_this_guard_exists_to_stop():
    # Nine real releases bumped the minor for a plain feature. Pre-1.0 that
    # slot is reserved, so the guard must refuse it.
    problems = guard.check("0.10.0", "0.11.0", FEATURE)
    assert problems and "reserved" in problems[0]


def test_a_breaking_change_must_move_the_contract_slot():
    problems = guard.check("0.10.0", "0.10.1", BREAK)
    assert problems and "BREAKING" in problems[0]


def test_a_breaking_change_on_the_contract_slot_passes():
    assert guard.check("0.10.0", "0.11.0", BREAK) == []


def test_post_1_0_a_feature_takes_the_minor():
    assert guard.check("1.0.0", "1.1.0", FEATURE) == []


def test_post_1_0_a_break_needs_the_major():
    assert guard.check("1.0.0", "1.1.0", BREAK) != []
    assert guard.check("1.0.0", "2.0.0", BREAK) == []


def test_the_1_0_commitment_needs_no_break():
    # 1.0 is a stability commitment, not necessarily a break; CONTRIBUTING
    # says so, and the guard must not demand a BREAKING entry for it.
    assert guard.check("0.10.1", "1.0.0", FIX) == []


def test_releases_that_predate_the_rule_are_left_alone():
    # 0.2.0 through 0.10.0 bumped the minor for features before the rule was
    # written. They are published and cannot be renumbered, so the guard must
    # not fail forever on history.
    assert guard.check("0.9.0", "0.10.0", FEATURE) == []
    assert guard.check("0.6.1", "0.7.0", FEATURE) == []
    assert guard.predates_the_rule("0.10.0")
    assert not guard.predates_the_rule("0.10.1")
    assert not guard.predates_the_rule("0.11.0")


def test_a_version_that_does_not_move_is_refused():
    assert guard.check("0.10.0", "0.10.0", FIX) != []


def test_a_version_that_goes_backwards_is_refused():
    assert guard.check("0.11.0", "0.10.0", FIX) != []


def test_an_empty_section_is_refused():
    assert guard.check("0.10.0", "0.10.1", "\n  \n") != []


# ---- reading the real CHANGELOG ----


def test_it_reads_this_repo_s_own_changelog():
    text = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text()
    versions = guard.released_versions(text)
    assert versions and versions[0] > versions[-1]  # newest first
    assert "Unreleased" not in versions  # carries no number to check
    body = guard.section_body(text, versions[0])
    assert body.strip()  # the newest release has notes


def test_breaking_is_recognised_in_both_spellings():
    assert guard.declares_breaking("- **BREAKING:** the schema moved")
    assert guard.declares_breaking("BREAKING CHANGE: the schema moved")
    assert not guard.declares_breaking("- added a non-breaking thing")
