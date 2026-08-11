"""The claude-code harness leaf: reading hooks out of that tool's own schema.

Vendor shapes live here, so the adapter above stays free of them.
"""

from planeops.adapters.harness.harnesses.claude_code import HARNESS, _hooks


def test_declaration_is_complete():
    assert HARNESS.label == "claude-code" and HARNESS.config and HARNESS.hooks


def test_reads_a_command_from_its_nested_schema():
    data = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "a.sh"}]}
            ]
        }
    }
    assert _hooks(data) == [("PreToolUse", "a.sh")]


def test_reads_every_group_and_every_hook_in_a_group():
    data = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"command": "a.sh"}, {"command": "b.sh"}],
                },
                {"matcher": "Edit", "hooks": [{"command": "c.sh"}]},
            ],
            "Stop": [{"hooks": [{"command": "d.sh"}]}],
        }
    }
    assert sorted(_hooks(data)) == [
        ("PreToolUse", "a.sh"),
        ("PreToolUse", "b.sh"),
        ("PreToolUse", "c.sh"),
        ("Stop", "d.sh"),
    ]


def test_settings_without_hooks_yields_none():
    assert _hooks({}) == []
    assert _hooks({"hooks": {}}) == []
    assert _hooks({"theme": "dark"}) == []


def test_a_malformed_shape_yields_what_it_can_rather_than_raising():
    # A settings file is the tool's, not ours: an unexpected shape in one
    # branch must not lose the hooks declared correctly in another.
    data = {
        "hooks": {
            "PreToolUse": "not-a-list",
            "Stop": [{"hooks": [{"command": "good.sh"}, "not-a-mapping"]}],
            "Other": [None],
        }
    }
    assert _hooks(data) == [("Stop", "good.sh")]


def test_an_empty_command_is_not_a_hook():
    data = {"hooks": {"Stop": [{"hooks": [{"command": "   "}, {"command": ""}]}]}}
    assert _hooks(data) == []
