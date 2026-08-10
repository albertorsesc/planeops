"""Check a release's version bump against what its CHANGELOG section says.

The rule (CONTRIBUTING.md): one slot means "a contract moved" — the minor
while 0.x, the major from 1.0 — and everything else is a patch. So a BREAKING
entry demands that slot, and moving that slot demands a BREAKING entry. The
number and the notes can never tell a reader two different stories.

    python scripts/check_version_bump.py

Reads `__version__` and the newest released CHANGELOG section, which is what a
`chore(release):` PR carries. Exit 0 when they agree, 1 when they do not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
INIT = ROOT / "planeops/__init__.py"

# A released section header, e.g. "## [0.10.1] - 2026-08-10". `Unreleased`
# deliberately does not match: it carries no number to check.
SECTION = re.compile(r"^## \[(\d+\.\d+\.\d+)\]")

# The one release that moves the contract slot without breaking anything: 1.0
# is a stability commitment, which CONTRIBUTING states outright.
COMMITMENT = "1.0.0"

# Releases up to here bumped the minor for features, before the rule was
# written down. They are history and cannot be renumbered, so the guard starts
# after them rather than failing forever on the past. CONTRIBUTING says the
# same in prose.
RULE_STARTS_AFTER = (0, 10, 0)


def released_versions(text: str) -> list[str]:
    return [m.group(1) for line in text.splitlines() if (m := SECTION.match(line))]


def section_body(text: str, version: str) -> str:
    """The notes for one version: everything up to the next `## ` header."""
    out: list[str] = []
    collecting = False
    for line in text.splitlines():
        if line.startswith("## "):
            if collecting:
                break
            m = SECTION.match(line)
            collecting = bool(m) and m.group(1) == version  # type: ignore[union-attr]
            continue
        if collecting:
            out.append(line)
    return "\n".join(out)


# A break is DECLARED by the marker CONTRIBUTING mandates: a bolded prefix on
# the entry itself (`- **BREAKING:**`, or `- **BREAKING (pre-1.0):**` as 0.1.0
# wrote it), or the commit-footer spelling. Anchored on purpose: the bare word
# appears in ordinary prose about the rule, and matching that made the guard
# refuse the very release that introduced it.
BREAKING_MARKER = re.compile(r"^\s*[-*]\s*\*\*BREAKING\b|^\s*BREAKING CHANGE:", re.M)


def declares_breaking(body: str) -> bool:
    return bool(BREAKING_MARKER.search(body))


def moved_slot(previous: str, current: str) -> str:
    """Which slot the bump moved: `contract` (reserved for breaking changes),
    `other` (feature or fix), `none`, or `backwards`."""
    p = tuple(int(x) for x in previous.split("."))
    c = tuple(int(x) for x in current.split("."))
    if c == p:
        return "none"
    if c < p:
        return "backwards"
    # Pre-1.0 the contract slot is the minor; from 1.0 it is the major.
    index = 1 if p[0] == 0 and c[0] == 0 else 0
    return "contract" if c[index] != p[index] else "other"


def predates_the_rule(version: str) -> bool:
    return tuple(int(x) for x in version.split(".")) <= RULE_STARTS_AFTER


def check(previous: str, version: str, body: str) -> list[str]:
    """Every disagreement between the bump and the notes; empty when they
    agree."""
    problems: list[str] = []
    if not body.strip():
        problems.append(f"the CHANGELOG section for {version} is empty")
    slot = moved_slot(previous, version)
    breaking = declares_breaking(body)
    # Structural checks hold for every release, including the grandfathered
    # ones: a version that stands still or goes backwards is wrong under any
    # numbering rule.
    if slot == "none":
        return problems + [f"version {version} does not move from {previous}"]
    if slot == "backwards":
        return problems + [f"version went backwards: {previous} -> {version}"]
    if predates_the_rule(version):
        return problems  # the slot rule starts after these; see CONTRIBUTING
    if breaking and slot != "contract":
        problems.append(
            f"{previous} -> {version} is a patch bump, but the notes declare a "
            "BREAKING change; a break must move the contract slot (the minor "
            "while 0.x, the major from 1.0)"
        )
    if slot == "contract" and not breaking and version != COMMITMENT:
        problems.append(
            f"{previous} -> {version} moves the contract slot, which is reserved "
            "for breaking changes, but the notes declare none; bump the patch "
            "instead, or add the BREAKING entry that justifies it"
        )
    return problems


def main() -> int:
    text = CHANGELOG.read_text(encoding="utf-8")
    versions = released_versions(text)
    if not versions:
        print("error: no released section in CHANGELOG.md", file=sys.stderr)
        return 1
    version = versions[0]

    declared = re.search(r'__version__ = "([^"]+)"', INIT.read_text(encoding="utf-8"))
    if not declared:
        print("error: no __version__ in planeops/__init__.py", file=sys.stderr)
        return 1
    if declared.group(1) != version:
        print(
            f"error: __version__ is {declared.group(1)} but the newest CHANGELOG "
            f"section is {version}; a release moves both together",
            file=sys.stderr,
        )
        return 1

    if len(versions) < 2:
        print(f"{version} is the first release; nothing to compare")
        return 0

    problems = check(versions[1], version, section_body(text, version))
    for p in problems:
        print(f"error: {p}", file=sys.stderr)
    if problems:
        return 1
    print(f"{versions[1]} -> {version}: the bump agrees with the notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
