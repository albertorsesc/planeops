"""claude-code: hooks in `settings.json`, under `hooks`.

The schema nests two levels below the event: each event holds a list of
matcher groups (which tools the hook applies to), and each group holds the
hooks themselves. Matchers are deliberately not read: they scope when a hook
fires, and a hook that fires on fewer tools still runs code unprompted, so
the matcher belongs to the hook's configuration rather than to its identity.
"""

from __future__ import annotations

from typing import Any

from planeops.adapters.harness import KnownHarness


def _hooks(data: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    events = data.get("hooks")
    if not isinstance(events, dict):
        return out
    for event, groups in events.items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            for hook in group.get("hooks") or []:
                command = hook.get("command") if isinstance(hook, dict) else None
                if isinstance(command, str) and command.strip():
                    out.append((str(event), command))
    return out


HARNESS = KnownHarness(label="claude-code", config="settings.json", hooks=_hooks)
