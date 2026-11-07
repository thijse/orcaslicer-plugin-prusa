"""Compare the printer's tools with Orca's filament slots (preset and colour), tool N = slot N."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from .material_swap import printer_type, type_change
from .materials import FilamentPreset, match_preset
from .model import ToolState


def parse_colours(value: Any) -> list[str]:
    """`filament_colour` as Orca hands it over: a list, or a ';'/','-separated string with quotes."""
    if value is None:
        return []
    items: Iterable[object] = (
        cast(Iterable[object], value) if isinstance(value, (list, tuple)) else str(value).replace(";", ",").split(",")
    )
    return [str(v).strip().strip('"').upper() for v in items if str(v).strip()]


def _hex(colour: str) -> str:
    return (colour or "").strip().upper()[:7]


def compare(
    tools: list[ToolState], presets: Iterable[FilamentPreset], slot_presets: list[str], slot_colours: list[str]
) -> list[dict[str, Any]]:
    presets = list(presets)
    rows: list[dict[str, Any]] = []
    for tool in tools:
        i = tool.index
        match: FilamentPreset | None = match_preset(tool, presets)
        slot = None
        if i < len(slot_presets):
            slot = {"preset": slot_presets[i], "color": slot_colours[i] if i < len(slot_colours) else ""}
        loaded = bool(tool.is_loaded and tool.material)
        color = _hex(tool.color) if loaded else ""
        slot_type = next((p.type for p in presets if slot and p.name == slot["preset"]), "")
        # A bare material type ("PLA") says nothing against a more specific preset of that type.
        specific = bool(tool.vendor or tool.name)
        preset_differs = bool(
            slot and match and slot["preset"] != match.name and (specific or slot_type.upper() != tool.material.upper())
        )
        rows.append(
            {
                "tool_number": tool.tool_number,
                "printer": {
                    "material": tool.material,
                    "name": tool.name,
                    "vendor": tool.vendor,
                    "color": color,
                    "loaded": loaded,
                },
                "match": match.name if match else "",
                "slot": slot,
                "preset_differs": preset_differs,
                "color_differs": bool(slot and color and _hex(slot["color"]) != color),
                # The Orca slot slices another material type than the printer has loaded.
                "type_differs": bool(loaded and slot_type and type_change(tool.material, slot_type)),
                "slot_type": printer_type(slot_type),
            }
        )
    return rows


def colours_from_printer(rows: list[dict[str, Any]], slot_colours: list[str]) -> list[str]:
    """The full slot colour list with the selected rows' slots set to their tool's colour."""
    out = list(slot_colours)
    for row in rows:
        i = row["tool_number"] - 1
        if i < len(out) and row["printer"]["color"]:
            out[i] = _hex(row["printer"]["color"])
    return out
