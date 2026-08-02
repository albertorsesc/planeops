"""ruamel.yaml provider: the only module allowed to know ruamel exists."""

from __future__ import annotations

import io
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

_safe = YAML(typ="safe")
_safe.default_flow_style = False
_rt = YAML()  # round-trip: preserves comments, order, and formatting
_rt.preserve_quotes = True

ParseError = YAMLError


def load(text: str) -> Any:
    return _safe.load(text)


def load_all(text: str) -> list[Any]:
    return list(_safe.load_all(text))


def dump(data: Any) -> str:
    # The round-trip emitter keeps dict insertion order (the safe one sorts
    # keys alphabetically, which scrambles manifests: id belongs first).
    buf = io.StringIO()
    _rt.dump(data, buf)
    return buf.getvalue()


def edit_load(text: str) -> Any:
    return _rt.load(text)


def edit_dump(data: Any) -> str:
    buf = io.StringIO()
    _rt.dump(data, buf)
    return buf.getvalue()
