"""A filament of another material type than the printer has loaded, and the swap that follows.

The printer's own material type decides: Connect refuses a spool of another type ("The tool material cannot be
edited"), and a remote LOAD_FILAMENT names no tool, so the XL ignores it. A new type therefore means unloading
(remotely or on the printer) and loading from the printer's menu; the full spool is recorded once the printer
reports the new type, because a menu load leaves only the type.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, fields
from typing import Any, cast

# The Buddy firmware's preset filament types (src/common/filament.hpp, PresetFilamentType); PPS and PPA only
# on high-temperature hotends. Load/unload temperatures and the print-start check use these names.
PRINTER_TYPES = ("PLA", "PETG", "ASA", "PC", "PVB", "ABS", "HIPS", "PP", "FLEX", "PA", "PPS", "PPA", "PVA", "BVOH")

# Every other type in Prusa Connect's catalogue (15.7k entries) and the Open Filament Database, mapped to the
# printer preset that loads and prints like it. Types with no close preset map to themselves.
_TYPE_MAP = {
    # PLA family: blends and PLA-like biopolymers
    "PLA+": "PLA",
    "PLAPRO": "PLA",
    "PLAPHA": "PLA",
    "PLAPHB": "PLA",
    "FLEXPLA": "PLA",
    "PLATPU": "PLA",
    "BIO": "PLA",
    "NICEBIO": "PLA",
    "BIOWOOD": "PLA",
    "WOOD": "PLA",
    "PHA": "PLA",
    "PCL": "PLA",
    # PETG family: copolyesters
    "PET": "PETG",
    "RPETG": "PETG",
    "PCTG": "PETG",
    "CPE": "PETG",
    "XT": "PETG",
    "NGEN": "PETG",
    # ABS family
    "ABS+": "ABS",
    "ABSPRO": "ABS",
    "SAN": "ABS",
    # PC family
    "PCABS": "PC",
    "PCPBT": "PC",
    "PCBLEND": "PC",
    # Polyamides
    "PA6": "PA",
    "PA11": "PA",
    "PA12": "PA",
    "PA612": "PA",
    "PAHT": "PA",
    # Flexibles
    "TPU": "FLEX",
    "TPE": "FLEX",
    "TPC": "FLEX",
    "PEBA": "FLEX",
    "SFLEX": "FLEX",
    # Polyolefins
    "HDPE": "PP",
    "PE": "PP",
}
_FILLERS = re.compile(r"(CF\d*|GF\d*|HF|ESD|SILK|MATTE|PRO|HS|\+)+$")


def printer_type(material: str) -> str:
    """The printer's type for `material`: "PLA+ Silk" -> "PLA", "PETG-CF" -> "PETG", "TPU" -> "FLEX", "PA12" -> "PA"."""
    words = re.sub(r"[^A-Z0-9+ ]+", " ", (material or "").upper()).split()
    if not words:
        return ""
    joined = "".join(words)
    if joined in _TYPE_MAP or joined in PRINTER_TYPES:
        return _TYPE_MAP.get(joined, joined)
    first = words[0]
    if first in _TYPE_MAP or first in PRINTER_TYPES:
        return _TYPE_MAP.get(first, first)
    base = _FILLERS.sub("", first) or first
    return _TYPE_MAP.get(base, base)


def compatible_types(loaded: str) -> list[str]:
    """Catalogue types that load and print like the loaded material: the printer type and everything mapped to it."""
    target = printer_type(loaded)
    if not target:
        return []
    return [target, *sorted(t for t, p in _TYPE_MAP.items() if p == target and t != target)]


def type_change(loaded: str, chosen: str) -> bool:
    """True when the chosen filament is another material type than the one loaded (nothing loaded: no change)."""
    a, b = printer_type(loaded), printer_type(chosen)
    return bool(a and b and a != b)


# How long a planned swap waits for the printer to report the new material.
SWAP_TIMEOUT = 45 * 60


@dataclass
class PlannedSwap:
    """A spool the user is about to load: recorded in Connect once the printer reports its type on the tool."""

    tool_number: int
    material: str  # printer type, e.g. "PETG"
    vendor: str
    name: str
    color: str
    title: str
    started: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(data: object) -> PlannedSwap | None:
        if not isinstance(data, dict):
            return None
        known = {f.name for f in fields(PlannedSwap)}
        values = cast(dict[str, Any], data)
        try:
            return PlannedSwap(**{k: v for k, v in values.items() if k in known})
        except TypeError:
            return None


def swap_progress(swap: PlannedSwap, loaded: str, is_loaded: bool, now: float | None = None) -> str:
    """ "done" when the printer reports the new type on the tool, "expired" after SWAP_TIMEOUT, else "waiting"."""
    if is_loaded and printer_type(loaded) == swap.material:
        return "done"
    if (now if now is not None else time.time()) - swap.started > SWAP_TIMEOUT:
        return "expired"
    return "waiting"
