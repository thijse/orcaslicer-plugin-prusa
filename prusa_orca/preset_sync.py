"""Compare the printer's per-tool nozzles with Orca's printer preset, in both directions.

The XL stores per tool a nozzle diameter and hardened/high-flow flags. Orca's printer preset
holds `nozzle_diameter` and `nozzle_type` per extruder. High flow has no counterpart in a Prusa
preset (Orca models it as a Bambu extruder variant), so it is shown but not synced.
"""

from __future__ import annotations

from typing import Any, Optional

from .model import ToolState

HARDENED_TYPES = ("hardened_steel", "tungsten_carbide")


def _list(value: Any) -> list[str]:
    """Orca hands over vector options either as a list or as a comma-separated string."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip().strip('"') for v in value]
    return [v.strip().strip('"') for v in str(value).split(",") if v.strip()]


def _float(text: str) -> Optional[float]:
    try:
        return float(text)
    except ValueError:
        return None


def compare(tools: list[ToolState], nozzle_diameter: Any, nozzle_type: Any) -> list[dict[str, Any]]:
    """One row per tool: what the printer has, what the preset has, and whether they differ."""
    diameters, types = _list(nozzle_diameter), _list(nozzle_type)
    rows = []
    # MMU slots share one nozzle: compare the head once.
    for tool in [t for t in tools if t.kind == "head"] or tools[:1]:
        i = tool.index
        preset_d = _float(diameters[i]) if i < len(diameters) else None
        preset_t = types[i] if i < len(types) else ""
        rows.append({
            "tool_number": tool.tool_number,
            "printer": {"diameter": tool.nozzle_diameter, "hardened": tool.hardened, "high_flow": tool.high_flow},
            "preset": {"diameter": preset_d, "type": preset_t, "hardened": preset_t in HARDENED_TYPES},
            "diameter_differs": preset_d is not None and abs(preset_d - tool.nozzle_diameter) > 1e-6,
            "hardened_differs": bool(preset_t) and (preset_t in HARDENED_TYPES) != tool.hardened,
        })
    return rows


def printer_to_preset(rows: list[dict[str, Any]], nozzle_diameter: Any, nozzle_type: Any) -> dict[str, str]:
    """Serialized `nozzle_diameter` / `nozzle_type` values that make the preset match the printer.

    A non-hardened nozzle keeps the preset's own soft type (brass or stainless) when it has one.
    Returns only the keys that change.
    """
    diameters, types = _list(nozzle_diameter), _list(nozzle_type)
    new_d, new_t = list(diameters), list(types)
    for row in rows:
        i = row["tool_number"] - 1
        if i >= len(new_d) or i >= len(new_t):
            continue
        if row["diameter_differs"]:
            new_d[i] = f"{row['printer']['diameter']:g}"
        if row["hardened_differs"]:
            new_t[i] = "hardened_steel" if row["printer"]["hardened"] else "brass"
    out = {}
    if new_d != diameters:
        out["nozzle_diameter"] = ",".join(new_d)
    if new_t != types:
        out["nozzle_type"] = ",".join(new_t)
    return out


def preset_to_printer(rows: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Connect commands that make the printer's tool settings match the preset."""
    commands: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        n = row["tool_number"]
        if row["diameter_differs"]:
            commands.append(("SET_TOOL_NOZZLE_DIAMETER", {"tool_number": n, "nozzle_diameter": row["preset"]["diameter"]}))
        if row["hardened_differs"]:
            commands.append(("SET_TOOL_HARDENED", {"tool_number": n, "hardened": row["preset"]["hardened"]}))
    return commands
