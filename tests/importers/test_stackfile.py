import yaml

from engine.importers.stackfile import (
    HeaderRule,
    load_rules,
    parse_stackfile,
    render_proposal,
)

STACK = """
# My Stack

## MCP Servers
- `example-server` (http)
- `another-server` stdio

## Skills
- example-skill

## Secrets / API Keys
- Some provider key

## Random Section
- something odd
"""

# The test supplies its own rules; the importer hardcodes none.
RULES = [
    HeaderRule("mcp", "mcp", "mcp-server"),
    HeaderRule("skill", "harness", "skill"),
    HeaderRule("secret", "manual", "secret"),
    HeaderRule("api key", "manual", "secret"),
]


def test_rules_map_headers_to_adapters():
    by_id = {e["id"]: e for e in parse_stackfile(STACK, RULES)}
    assert by_id["mcp/example-server"]["adapter"] == "mcp"
    assert by_id["mcp/example-server"]["domain"] == "mcp-server"
    assert by_id["harness/example-skill"]["domain"] == "skill"


def test_secret_headers_map_per_rules():
    secret = next(e for e in parse_stackfile(STACK, RULES) if e["domain"] == "secret")
    assert secret["adapter"] == "manual"


def test_unmatched_header_falls_back_to_manual_unknown():
    odd = next(
        e for e in parse_stackfile(STACK, RULES) if e["id"].endswith("/something-odd")
    )
    assert odd["adapter"] == "manual" and odd["domain"] == "unknown"


def test_no_rules_imports_everything_as_manual():
    entries = parse_stackfile(STACK, [])
    assert entries and all(e["adapter"] == "manual" for e in entries)


def test_every_entry_marked_for_verification():
    for e in parse_stackfile(STACK, RULES):
        assert e["intent"] == "imported from manifest, verify"
        assert e["lifecycle"] == "active"


def test_proposal_is_valid_yaml_roundtrip():
    entries = parse_stackfile(STACK, RULES)
    loaded = yaml.safe_load(render_proposal(entries))
    assert loaded["entries"] == entries


def test_load_rules_reads_the_mapping_file(tmp_path):
    (tmp_path / "stackfile-mapping.yaml").write_text(
        "rules:\n  - keyword: mcp\n    adapter: mcp\n    domain: mcp-server\n"
    )
    assert load_rules(tmp_path) == [HeaderRule("mcp", "mcp", "mcp-server")]


def test_load_rules_missing_is_empty():
    assert load_rules(None) == []
