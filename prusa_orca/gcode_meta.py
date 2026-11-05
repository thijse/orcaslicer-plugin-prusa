"""What an Orca-sliced plate needs, read from the G-code's header and config comments."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# The config block and the time/filament summary sit at the end of the file.
_TAIL_BYTES = 512 * 1024
_HEAD_BYTES = 64 * 1024


@dataclass
class GcodeMeta:
    filament_types: list[str] = field(default_factory=list)
    filament_presets: list[str] = field(default_factory=list)
    filament_colours: list[str] = field(default_factory=list)
    nozzle_diameters: list[float] = field(default_factory=list)
    used_tools: list[int] = field(default_factory=list)  # 0-based tools the G-code selects (T<n>)
    filament_used_g: list[float] = field(default_factory=list)
    estimated_seconds: int = 0
    printer_model: str = ""
    printer_preset: str = ""
    high_flow: bool = False  # sliced with a high-flow nozzle preset
    required_hrc: list[int] = field(default_factory=list)  # per filament; > 0 needs a hardened nozzle

    def used(self, index: int) -> bool:
        return index in self.used_tools if self.used_tools else index < len(self.filament_types)

    def abrasive(self, index: int) -> bool:
        """Filament `index` wears a brass nozzle: the preset asks for a hard nozzle, or it is a CF/GF blend."""
        if index < len(self.required_hrc) and self.required_hrc[index] > 0:
            return True
        kind = self.filament_types[index].upper() if index < len(self.filament_types) else ""
        return bool(re.search(r"(^|[-+ ])(CF|GF)\d*\b|-(CF|GF)", kind))


def _split(value: str) -> list[str]:
    return [v.strip().strip('"') for v in re.split(r"[;,]", value) if v.strip()]


def _floats(value: str) -> list[float]:
    out = []
    for v in _split(value):
        try:
            out.append(float(v))
        except ValueError:
            out.append(0.0)
    return out


def parse_duration(text: str) -> int:
    """'1d 2h 3m 4s' -> seconds."""
    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(int(n) * units[u] for n, u in re.findall(r"(\d+)\s*([dhms])", text))


def parse_text(text: str) -> GcodeMeta:
    meta = GcodeMeta()
    notes = ""
    for line in text.splitlines():
        if not line.startswith(";"):
            continue
        key, sep, value = line[1:].partition("=")
        if not sep:
            if "total estimated time:" in line:
                meta.estimated_seconds = parse_duration(line.split("total estimated time:", 1)[1])
            continue
        key, value = key.strip(), value.strip()
        if key == "filament_type":
            meta.filament_types = _split(value)
        elif key == "filament_settings_id":
            meta.filament_presets = _split(value)
        elif key in ("filament_colour", "extruder_colour") and not meta.filament_colours:
            meta.filament_colours = [c.upper() for c in _split(value)]
        elif key == "nozzle_diameter":
            meta.nozzle_diameters = _floats(value)
        elif key == "filament used [g]":
            meta.filament_used_g = _floats(value)
        elif key == "printer_model":
            meta.printer_model = value
        elif key == "printer_settings_id":
            meta.printer_preset = value.strip('"')
        elif key == "printer_notes":
            notes = value
        elif key == "required_nozzle_HRC":
            meta.required_hrc = [int(v) for v in _floats(value)]
        elif key.startswith("estimated printing time") and not meta.estimated_seconds:
            meta.estimated_seconds = parse_duration(value)
    # Prusa's HF presets tag printer_notes with HF_NOZZLE (their start G-code tells the printer the same).
    meta.high_flow = "HF_NOZZLE" in notes or bool(re.search(r"\bHF\b", f"{meta.printer_model} {meta.printer_preset}"))
    return meta


def from_summary(data: dict) -> GcodeMeta:
    """The metadata a history record kept (see `summary`)."""
    names = {f for f in GcodeMeta.__dataclass_fields__}
    return GcodeMeta(**{k: v for k, v in (data or {}).items() if k in names})


def read(path: str) -> GcodeMeta:
    """Metadata of a G-code file, plus the tools it selects (scanned from the whole file)."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(_HEAD_BYTES)
        f.seek(max(0, size - _TAIL_BYTES))
        tail = f.read()
        f.seek(0)
        tools: set[int] = set()
        pattern = re.compile(rb"^T(\d+)\s*(?:;|$)", re.M)
        while chunk := f.read(1 << 22):
            tools.update(int(m) for m in pattern.findall(chunk))
    meta = parse_text((head + b"\n" + tail).decode("utf-8", "replace"))
    meta.used_tools = sorted(t for t in tools if t < 32)
    return meta


def summary(meta: GcodeMeta | None) -> dict:
    if meta is None:
        return {}
    return {"filament_types": meta.filament_types, "filament_presets": meta.filament_presets,
            "filament_colours": meta.filament_colours, "used_tools": meta.used_tools,
            "filament_used_g": meta.filament_used_g, "estimated_seconds": meta.estimated_seconds,
            "nozzle_diameters": meta.nozzle_diameters, "printer_model": meta.printer_model,
            "printer_preset": meta.printer_preset, "high_flow": meta.high_flow, "required_hrc": meta.required_hrc}
