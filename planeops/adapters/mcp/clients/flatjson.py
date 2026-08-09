"""The shared editor for clients whose servers live in a flat mapping under
one top-level JSON key. A leaf opts in by naming these functions in its
`CLIENT`; the functions are pure (new mapping out, inputs untouched) and
preserve key order and every value object by reference, so an `env` sub-dict
crosses the edit untouched.

This is deliberately a value the leaf NAMES, never selected by inspecting
`format`: a format-to-editor table would be the central edit the seam exists
to avoid.
"""

from __future__ import annotations

from typing import Any


def remove_server(data: dict[str, Any], key: str, name: str) -> dict[str, Any]:
    """`data` with the server `name` gone from the mapping under `key`.
    Raises KeyError when `key` or `name` is absent: the caller verified both
    against a digest, so absence means the file changed underneath."""
    servers = data[key]
    if name not in servers:
        raise KeyError(name)
    return {**data, key: {k: v for k, v in servers.items() if k != name}}
