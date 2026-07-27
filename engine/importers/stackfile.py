"""Import a hand-maintained manifest of a machine's stack into proposed entries.

The section-to-adapter mapping is configuration, not code. Rules live in
`stackfile-mapping.yaml` at the instance root (see `stackfile-mapping.example.yaml`)
and are loaded per import, so the importer names no specific tool. A section that
no rule matches imports as `manual`, for a human to sort out. Nothing is written;
the CLI prints the proposal for review, and every row is marked for verification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

MAPPING_FILE = "stackfile-mapping.yaml"

_HEADER_RE = re.compile(r"^#{1,6}\s+(.*\S)\s*$")
_ITEM_RE = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")


@dataclass(frozen=True, slots=True)
class HeaderRule:
    keyword: str  # matched case-insensitively as a substring of a section header
    adapter: str
    domain: str


def load_rules(repo_root: Path | None) -> list[HeaderRule]:
    """Read section->adapter rules from `<repo_root>/stackfile-mapping.yaml`.
    Missing file or root yields no rules (every section then imports as manual)."""
    if repo_root is None:
        return []
    path = repo_root / MAPPING_FILE
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text())
    except (yaml.YAMLError, OSError):
        return []
    raw = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    rules: list[HeaderRule] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        keyword = item.get("keyword")
        adapter = item.get("adapter")
        domain = item.get("domain")
        if (
            isinstance(keyword, str)
            and isinstance(adapter, str)
            and isinstance(domain, str)
        ):
            rules.append(HeaderRule(keyword.lower(), adapter, domain))
    return rules


def _map_header(header: str, rules: list[HeaderRule]) -> tuple[str, str]:
    low = header.lower()
    for rule in rules:
        if rule.keyword in low:
            return rule.adapter, rule.domain
    return "manual", "unknown"


def _slug(text: str) -> str:
    # First backticked token, else the leading words, slugified.
    m = re.search(r"`([^`]+)`", text)
    base = m.group(1) if m else text
    base = base.split(":", 1)[0].split("(", 1)[0].split("—", 1)[0].split(" - ", 1)[0]
    slug = re.sub(r"[^a-z0-9]+", "-", base.strip().lower()).strip("-")
    return slug or "item"


def parse_stackfile(text: str, rules: list[HeaderRule]) -> list[dict[str, Any]]:
    """Return proposed entry mappings. Heuristic and lossy by design: every row
    imports with intent 'verify' so a human reviews before it is trusted."""
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    adapter, domain = "manual", "unknown"

    for line in text.splitlines():
        header = _HEADER_RE.match(line)
        if header:
            adapter, domain = _map_header(header.group(1), rules)
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
                "intent": "imported from manifest, verify",
            }
        )
    return entries


def render_proposal(entries: list[dict[str, Any]]) -> str:
    return yaml.safe_dump({"entries": entries}, sort_keys=False, allow_unicode=True)
