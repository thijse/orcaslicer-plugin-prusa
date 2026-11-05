"""Map printer tool materials to OrcaSlicer filament presets for AMS-style sync."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from .model import ToolState


@dataclass
class FilamentPreset:
    name: str
    filament_id: str = ""
    vendor: str = ""
    type: str = ""
    compatible: bool = True


class FilamentIdResolver:
    """filament_id of a preset, read from its JSON and its inherits chain (Orca's Python API does not expose it).

    System presets inherit by name inside their vendor folder; user presets name a system parent.
    """

    def __init__(self, system_dir: str) -> None:
        self.system_dir = system_dir
        self._by_name: Optional[dict[str, str]] = None
        self._cache: dict[str, str] = {}

    def _index(self) -> dict[str, str]:
        if self._by_name is None:
            self._by_name = {}
            try:
                vendors = os.listdir(self.system_dir)
            except OSError:
                vendors = []
            for vendor in vendors:
                folder = os.path.join(self.system_dir, vendor, "filament")
                try:
                    names = os.listdir(folder)
                except OSError:
                    continue
                for file in names:
                    if file.endswith(".json"):
                        self._by_name.setdefault(file[:-5], os.path.join(folder, file))
        return self._by_name

    @staticmethod
    def _read(path: str) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def resolve(self, preset_file: str) -> str:
        if preset_file in self._cache:
            return self._cache[preset_file]
        path, seen, result = preset_file, set(), ""
        while path and path not in seen:
            seen.add(path)
            data = self._read(path)
            if data.get("filament_id"):
                result = str(data["filament_id"])
                break
            parent = data.get("inherits")
            if isinstance(parent, list):
                parent = parent[0] if parent else ""
            # A sibling in the same folder first (system chains), then any vendor (user presets).
            sibling = os.path.join(os.path.dirname(path), f"{parent}.json") if parent else ""
            path = sibling if sibling and os.path.isfile(sibling) else self._index().get(parent or "", "")
        self._cache[preset_file] = result
        return result


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def match_preset(tool: ToolState, presets: Iterable[FilamentPreset]) -> Optional[FilamentPreset]:
    """Best compatible preset: exact vendor+name, then vendor+type, then Generic <type>, then any of the type."""
    if not tool.is_loaded or not tool.material:
        return None
    material = _norm(tool.material)
    candidates = [p for p in presets if p.compatible and _norm(p.type) == material]
    if not candidates:
        return None
    vendor = _norm(tool.vendor)
    name = _norm(tool.name)

    def score(p: FilamentPreset) -> tuple:
        base = _norm(p.name.split("@", 1)[0])
        return (
            bool(vendor and name and vendor in base and name in base),
            bool(vendor and (_norm(p.vendor) == vendor or vendor in base)),
            base.startswith("generic"),
            -len(base),
        )

    return max(candidates, key=score)


def pick_connect_material(nodes: list[dict], vendor: str, name: str, material_type: str,
                          color: str = "") -> Optional[dict]:
    """Best Connect material-database entry for an Orca filament: same type, then vendor, name words and colour."""
    want_type = _norm(material_type)
    want_vendor = _norm(vendor)
    want_words = set(_norm(name).split()) - set(want_vendor.split()) - {want_type}
    want_color = (color or "").lstrip("#").upper()[:6]

    def score(node: dict) -> tuple:
        m = node.get("material") or {}
        brand = _norm((m.get("brand") or {}).get("name") or "")
        words = set(_norm(m.get("name") or "").split())
        return (
            _norm(m.get("abbreviation") or "") == want_type,
            bool(brand) and (brand == want_vendor or brand in want_words),
            len(want_words & (words | {brand})),
            bool(want_color) and ((m.get("primaryColor") or {}).get("colorRgba") or "").lstrip("#").upper()[:6] == want_color,
            -len(words - want_words),
        )

    candidates = [n for n in nodes if _norm((n.get("material") or {}).get("abbreviation") or "") == want_type]
    return max(candidates, key=score) if candidates else None


def tray_info_idx(tool: ToolState, preset: Optional[FilamentPreset]) -> str:
    # Orca falls back to "Generic <type>" for an unknown non-empty id; never use a 'P'-prefixed id (Bambu-only).
    if preset and preset.filament_id:
        return preset.filament_id
    return f"PRUSA-{tool.material or 'UNKNOWN'}"
