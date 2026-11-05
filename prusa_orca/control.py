"""Printer controls (temperatures, speed, motion) through Prusa Connect, which allows more than PrusaLink.

Orca's Device tab sends Bambu-style G-code lines and JSON; these map them onto Connect commands.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Printers don't report their limits; these are the XL/MK4/CORE One firmware caps (see printers.py).
NOZZLE_MAX = 290
BED_MAX = 120


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def gcode_to_commands(gcode: str, nozzle_max: int = NOZZLE_MAX, bed_max: int = BED_MAX) -> list[tuple[str, dict[str, Any]]]:
    """Translate the G-code lines Orca's Device tab sends into Connect commands. Unknown lines are skipped."""
    commands: list[tuple[str, dict[str, Any]]] = []
    relative = False
    for raw in gcode.replace("\\n", "\n").splitlines():
        line = raw.split(";", 1)[0].strip().upper()
        if not line:
            continue
        word = line.split()[0]
        args = {m.group(1): float(m.group(2)) for m in re.finditer(r"([A-Z])(-?\d+(?:\.\d+)?)", line[len(word):])}
        if word in ("M104", "M109") and "S" in args:
            commands.append(("SET_NOZZLE_TEMPERATURE", {"nozzle_temperature": int(_clamp(args["S"], 0, nozzle_max))}))
        elif word in ("M140", "M190") and "S" in args:
            commands.append(("SET_HEATBED_TEMPERATURE", {"bed_temperature": int(_clamp(args["S"], 0, bed_max))}))
        elif word == "M220" and "S" in args:
            commands.append(("SET_SPEED", {"speed": int(_clamp(args["S"], 10, 200))}))
        elif word == "G28":
            axes = "".join(a for a in "XYZ" if a in line[3:]) or "XYZ"
            commands.append(("HOME", {"axis": axes}))
        elif word == "G91":
            relative = True
        elif word == "G90":
            relative = False
        elif word in ("G0", "G1") and relative:
            feed = int(args.get("F", 3000))
            if "X" in args or "Y" in args:
                move: dict[str, Any] = {"feedrate": feed}
                for axis in "XY":
                    if axis in args:
                        move[axis.lower()] = args[axis]
                commands.append(("MOVE", move))
            if "Z" in args:
                commands.append(("MOVE_Z", {"feedrate": min(feed, 600), "distance": args["Z"]}))
    return commands


def is_allowed(supported: dict[str, list[str]], command: str, state: Optional[str]) -> bool:
    states = supported.get(command)
    return states is not None and (state is None or state.upper() in states)
