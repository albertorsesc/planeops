"""Import a hand-maintained `stack.md`-style manifest into proposed entries.

Mapping follows SPEC.md section 6. The importer always emits the FINAL adapter
name (even when that adapter is not yet implemented, so the entry surfaces under
Uncovered rather than as a violation). Rows with no planned adapter map to
`manual`. Nothing is written; the CLI prints the proposal for the human to edit.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

# (header keyword, adapter, domain). First keyword found in a header wins.
_MAPPING: list[tuple[str, str, str]] = [
    ("machine", "manual", "host"),
    ("runtime", "launchd", "service"),
    ("agent execution", "launchd", "service"),
    ("browser", "pkg-npm", "package"),
    ("infrastructure", "manual", "service"),
    ("custom system", "manual", "project"),
    ("mcp", "mcp-json", "mcp-server"),
    ("skill", "claude-code", "skill"),
    ("secret", "manual", "secret"),
    ("api key", "manual", "secret"),
    ("subscription", "manual", "secret"),
]

_HEADER_RE = re.compile(r"^#{1,6}\s+(.*\S)\s*$")
_ITEM_RE = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")


def _map_header(header: str) -> tuple[str, str]:
    low = header.lower()
    for keyword, adapter, domain in _MAPPING:
        if keyword in low:
            return adapter, domain
    return "manual", "unknown"


def _slug(text: str) -> str:
    # First backticked token, else the leading words, slugified.
    m = re.search(r"`([^`]+)`", text)
    base = m.group(1) if m else text
    base = base.split(":", 1)[0].split("(", 1)[0].split("—", 1)[0].split(" - ", 1)[0]
    slug = re.sub(r"[^a-z0-9]+", "-", base.strip().lower()).strip("-")
    return slug or "item"


def parse_stackfile(text: str) -> list[dict[str, Any]]:
    """Return proposed entry mappings. Heuristic and lossy by design: every
    row imports with intent 'verify' so a human reviews before it is trusted."""
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    adapter, domain = "manual", "unknown"

    for line in text.splitlines():
        header = _HEADER_RE.match(line)
        if header:
            adapter, domain = _map_header(header.group(1))
            continue
        item = _ITEM_RE.match(line)
        if not item:
            continue
        native = _slug(item.group(1))
        entry_id = f"{adapter}/{native}"
        if entry_id in seen:
            continue
        seen.add(entry_id)
        entries.append(
            {
                "id": entry_id,
                "adapter": adapter,
                "domain": domain,
                "lifecycle": "active",
                "tolerance": "report",
                "intent": "imported from stack.md, verify",
            }
        )
    return entries


def render_proposal(entries: list[dict[str, Any]]) -> str:
    return yaml.safe_dump({"entries": entries}, sort_keys=False, allow_unicode=True)
