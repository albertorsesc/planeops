import yaml

from engine.importers.stackfile import parse_stackfile, render_proposal

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


def test_maps_headers_to_final_adapter_names():
    entries = parse_stackfile(STACK)
    by_id = {e["id"]: e for e in entries}
    assert by_id["mcp-json/example-server"]["adapter"] == "mcp-json"
    assert by_id["mcp-json/example-server"]["domain"] == "mcp-server"
    assert "claude-code/example-skill" in by_id
    assert by_id["claude-code/example-skill"]["domain"] == "skill"


def test_secret_headers_map_to_manual_secret():
    entries = parse_stackfile(STACK)
    secret = next(e for e in entries if e["domain"] == "secret")
    assert secret["adapter"] == "manual"


def test_unmapped_header_falls_back_to_manual_unknown():
    entries = parse_stackfile(STACK)
    odd = next(e for e in entries if e["id"].endswith("/something-odd"))
    assert odd["adapter"] == "manual" and odd["domain"] == "unknown"


def test_every_entry_marked_for_verification():
    for e in parse_stackfile(STACK):
        assert e["intent"] == "imported from stack.md, verify"
        assert e["lifecycle"] == "active"


def test_proposal_is_valid_yaml_roundtrip():
    entries = parse_stackfile(STACK)
    loaded = yaml.safe_load(render_proposal(entries))
    assert loaded["entries"] == entries
