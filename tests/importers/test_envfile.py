import yaml

from engine.importers.envfile import (
    entries_from_names,
    parse_envfile,
    render_proposal,
)

ENV = """
# an example env file
export OPENROUTER_API_KEY=sk-secret-value-123
ANTHROPIC_API_KEY="another-secret"
DB_PASSWORD='p@ss word'
NOT_A_SECRET_LINE
BASE64_TOKEN=abc=def==
BLANK=
"""

_VALUES = ["sk-secret-value-123", "another-secret", "p@ss", "abc=def"]


def test_parse_extracts_names_never_values():
    names = parse_envfile(ENV)
    assert names == [
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "DB_PASSWORD",
        "BASE64_TOKEN",
        "BLANK",
    ]
    blob = " ".join(names)
    for v in _VALUES:
        assert v not in blob  # a value never survives parsing


def test_lines_without_an_assignment_are_skipped():
    assert parse_envfile("JUST_A_NAME\n# comment\n\n   \n") == []


def test_names_are_deduped_in_order():
    assert parse_envfile("A=1\nB=2\nA=3\n") == ["A", "B"]


def test_entries_are_names_only_interactive_secret_stubs():
    assert entries_from_names(["OPENROUTER_API_KEY"]) == [
        {
            "id": "secrets/openrouter-api-key",
            "adapter": "secrets",
            "domain": "secret",
            "lifecycle": "active",
            "auth": "interactive",
            "intent": (
                "imported from env file; store the value in the sops store, then verify"
            ),
        }
    ]


def test_render_is_valid_yaml_and_leaks_no_value():
    out = render_proposal(entries_from_names(parse_envfile(ENV)))
    for v in _VALUES:
        assert v not in out
    loaded = yaml.safe_load(out)
    assert [e["id"] for e in loaded["entries"]] == [
        "secrets/openrouter-api-key",
        "secrets/anthropic-api-key",
        "secrets/db-password",
        "secrets/base64-token",
        "secrets/blank",
    ]
