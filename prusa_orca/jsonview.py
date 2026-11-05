"""Typed reads from untrusted JSON (printer, Prusa Connect, settings files).

API answers change between firmware and server versions, so every read checks the type and falls back to a
default instead of raising or passing an unexpected value on.
"""

from __future__ import annotations

from typing import Any, cast

JsonObj = dict[str, Any]


def obj(value: object, *path: str) -> JsonObj:
    """The object at `path` (each step a key), or {} when any step is missing or not an object."""
    for key in path:
        value = cast(JsonObj, value).get(key) if isinstance(value, dict) else None
    return cast(JsonObj, value) if isinstance(value, dict) else {}


def objs(value: object, *path: str) -> list[JsonObj]:
    """The objects in the list at `path`; non-object items are skipped."""
    parent = obj(value, *path[:-1]) if path else None
    items = parent.get(path[-1]) if parent is not None and path else value
    return [cast(JsonObj, i) for i in cast(list[object], items) if isinstance(i, dict)] if isinstance(items, list) else []


def text(value: object, key: str, default: str = "") -> str:
    v = obj(value).get(key)
    return v if isinstance(v, str) else (str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default)


def number(value: object, key: str, default: float = 0.0) -> float:
    v = obj(value).get(key)
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return default
    return default


def integer(value: object, key: str, default: int = 0) -> int:
    return int(number(value, key, default))


def flag(value: object, key: str, default: bool = False) -> bool:
    v = obj(value).get(key)
    return v if isinstance(v, bool) else default
