"""The filament catalogue: Prusa Connect and the Open Filament Database merged, and imported as Orca presets.

Pure logic; the backends fetch the data and the app writes the preset. Connect wins over OFD wherever both
have a value, and a Prusa printer's own Prusament profile wins over both.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, cast

from .jsonview import JsonObj, flag, number, obj, objs, text
from .materials import FilamentPreset

SOURCE_CONNECT = "connect"
SOURCE_OFD = "ofd"


@dataclass
class CatalogEntry:
    """One filament colour from either database, in one shape."""

    brand: str
    name: str
    type: str
    color: str = ""  # "#rrggbb"
    source: str = SOURCE_CONNECT
    key: str = ""  # stable id within its source
    connect_uuid: str = ""  # set when Connect has this filament: needed to record it on a printer tool
    tags: list[str] = field(default_factory=list)
    temps: dict[str, float] = field(default_factory=dict)  # min/max nozzle and bed, density, drying...
    url: str = ""

    @property
    def title(self) -> str:
        name = self.name
        if self.brand and not _norm(name).startswith(_norm(self.brand)):
            name = f"{self.brand} {name}"
        return name

    def view(self) -> dict[str, Any]:
        return {
            "key": f"{self.source}:{self.key}",
            "brand": self.brand,
            "brand_key": brand_key(self.brand),
            "name": self.name,
            "title": self.title,
            "type": self.type,
            "color": self.color,
            "source": self.source,
            "tags": self.tags,
            "has_data": bool(self.temps),
        }


def _norm(value: str) -> str:
    # "+" stays: "PLA+" is a different product from "PLA".
    return re.sub(r"[^a-z0-9+]+", " ", (value or "").lower()).strip()


def _clean(name: str) -> str:
    """A product name without trademark signs ("PolyLite™ PLA" -> "PolyLite PLA")."""
    return re.sub(r"\s+", " ", re.sub(r"[\u2122\u00ae\u00a9]", "", name)).strip()


def _hex(rgba: str) -> str:
    rgba = (rgba or "").lstrip("#")
    return f"#{rgba[:6].lower()}" if len(rgba) >= 6 else ""


CONNECT_PROPS = {
    "minPrintTemperature": "min_nozzle",
    "maxPrintTemperature": "max_nozzle",
    "minBedTemperature": "min_bed",
    "maxBedTemperature": "max_bed",
    "density": "density",
    "chamberTemperature": "chamber",
}


def connect_entry(node: JsonObj) -> CatalogEntry | None:
    """A Connect warehouse material node (`{material: {...}}`) as a catalogue entry."""
    m = obj(node, "material")
    uuid = text(m, "uuid")
    if not uuid or text(m, "class", default="FFF") != "FFF":
        return None
    props = obj(m, "properties")
    temps = {key: v for src, key in CONNECT_PROPS.items() if (v := number(props, src)) > 0}
    tags: object = m.get("tags")
    return CatalogEntry(
        brand=text(obj(m, "brand"), "name"),
        name=_clean(text(m, "name")),
        # "type" can be a product line ("PLA Pro"); the abbreviation is the material.
        type=text(m, "abbreviation") or text(m, "type"),
        color=_hex(text(obj(m, "primaryColor"), "colorRgba")),
        source=SOURCE_CONNECT,
        key=uuid,
        connect_uuid=uuid,
        tags=[t for t in cast(list[object], tags) if isinstance(t, str)] if isinstance(tags, list) else [],
        temps=temps,
        url=text(m, "url"),
    )


OFD_PROPS = {
    "min_print_temperature": "min_nozzle",
    "max_print_temperature": "max_nozzle",
    "min_bed_temperature": "min_bed",
    "max_bed_temperature": "max_bed",
    "density": "density",
    "chamber_temperature": "chamber",
}


def ofd_entries(dump: JsonObj) -> list[CatalogEntry]:
    """Every colour variant in an Open Filament Database dump (json/all.json) as catalogue entries."""
    brands = {text(b, "id"): text(b, "name") for b in objs(dump, "brands")}
    filaments = {text(f, "id"): f for f in objs(dump, "filaments")}
    out: list[CatalogEntry] = []
    for v in objs(dump, "variants"):
        f = filaments.get(text(v, "filament_id"))
        if f is None or flag(f, "discontinued") or flag(v, "discontinued"):
            continue
        temps = {key: x for src, key in OFD_PROPS.items() if (x := number(f, src)) > 0}
        name = _clean(text(f, "name"))
        brand = brands.get(text(f, "brand_id"), "")
        colour = text(v, "name")
        out.append(
            CatalogEntry(
                brand=brand,
                name=f"{name} {colour}".strip() if colour and _norm(colour) not in _norm(name) else name,
                type=text(f, "material"),
                color=_hex(text(v, "color_hex")),
                source=SOURCE_OFD,
                key=text(v, "id"),
                temps=temps,
                url=text(f, "data_sheet_url"),
            )
        )
    return out


# Suffixes brands carry in one database but not the other ("eSUN 3D" vs "eSUN").
_BRAND_NOISE = {"3d", "filament", "filaments", "official", "store", "lab"}


def brand_key(brand: str) -> str:
    words = [w for w in _norm(brand).split() if w not in _BRAND_NOISE]
    return " ".join(words) or _norm(brand)


def base_material(material: str) -> str:
    """The material without a product-line suffix: Connect files "PLA+" under "PLA Pro", OFD under "PLA"."""
    first = _norm(material).split()
    return first[0].rstrip("+") if first else ""


def _match_key(e: CatalogEntry) -> tuple[str, str, str]:
    brand = brand_key(e.brand)
    words = [w for w in _norm(e.name).split() if w not in brand.split() and w not in _norm(e.brand).split()]
    return brand, base_material(e.type), " ".join(sorted(words))


def merge(connect: Iterable[CatalogEntry], ofd: Iterable[CatalogEntry]) -> list[CatalogEntry]:
    """One list: Connect entries, gaps filled from the matching OFD entry, then OFD entries Connect lacks."""
    by_key: dict[tuple[str, str, str], CatalogEntry] = {}
    for e in ofd:
        by_key.setdefault(_match_key(e), e)
    out: list[CatalogEntry] = []
    used: set[tuple[str, str, str]] = set()
    for e in connect:
        k = _match_key(e)
        other = by_key.get(k)
        if other is not None:
            used.add(k)
            e.temps = {**other.temps, **e.temps}
            e.color = e.color or other.color
            e.url = e.url or other.url
        out.append(e)
    out.extend(e for k, e in by_key.items() if k not in used)
    return out


def search(
    entries: Iterable[CatalogEntry], query: str = "", brand: str = "", material: str = "", limit: int = 60
) -> list[CatalogEntry]:
    """Entries whose words all appear in brand+name+type, Prusament first, then by brand and name."""
    words = _norm(query).split()
    want_brand, want_type = _norm(brand), _norm(material)
    hits: list[CatalogEntry] = []
    for e in entries:
        hay = f"{_norm(e.brand)} {_norm(e.name)} {_norm(e.type)}".split()
        brand_ok = not want_brand or brand_key(e.brand) == brand_key(want_brand)
        if all(any(h.startswith(w) for h in hay) for w in words) and brand_ok and (not want_type or _norm(e.type) == want_type):
            hits.append(e)

    def rank(e: CatalogEntry) -> tuple[bool, int, str, str]:
        # Whole-word matches first ("PLA+" before "PLA+HS"), Prusament first among equals.
        hay = set(f"{_norm(e.brand)} {_norm(e.name)} {_norm(e.type)}".split())
        return (brand_key(e.brand) != "prusament", -sum(w in hay for w in words), brand_key(e.brand), _norm(e.name))

    hits.sort(key=rank)
    return hits[:limit]


# Material types that print like another one when Orca has no base of their own.
SIMILAR = {"PCTG": "PETG", "CPE": "PETG", "PLA+": "PLA", "TPU": "FLEX", "TPE": "FLEX", "HIPS": "ABS", "PC": "PC BLEND"}


def pick_base(entry: CatalogEntry, presets: Iterable[FilamentPreset]) -> tuple[FilamentPreset | None, str]:
    """The Orca preset an imported filament inherits from, and why: the same Prusament product,
    else a preset of the same type (Prusa's generic first), else one of a similar type."""
    compatible = [p for p in presets if p.compatible]

    def of_type(material: str) -> list[FilamentPreset]:
        return [p for p in compatible if _norm(p.type) == _norm(material)]

    if _norm(entry.brand) == "prusament":
        words = set(_norm(entry.name).split())
        same = [p for p in of_type(entry.type) if "prusament" in _norm(p.name)]
        exact = [p for p in same if set(_norm(p.name.split("@", 1)[0]).split()) - {"prusament"} <= words]
        if exact:
            return max(exact, key=lambda p: len(p.name.split("@", 1)[0])), "Prusa's own profile for this filament"
    base_type = base_material(entry.type).upper()
    tries = (
        (entry.type, f"the {entry.type} profile"),
        (base_type, ""),
        (SIMILAR.get(entry.type.upper(), ""), ""),
        (SIMILAR.get(base_type, ""), ""),
    )
    for material, why in tries:
        candidates = of_type(material) if material else []
        if candidates:
            generic = [p for p in candidates if _norm(p.name).startswith("generic")]
            base = (generic or candidates)[0]
            return base, why or f"the closest material, {material}"
    return None, f"no {entry.type or 'matching'} profile for this printer"


# Orca refuses a preset file without a parseable "version"; an old one loads in every release.
PRESET_VERSION = "2.0.0.0"


def _mid(lo: float | None, hi: float | None) -> int | None:
    if lo is None and hi is None:
        return None
    value = ((lo or hi or 0) + (hi or lo or 0)) / 2
    return int(round(value / 5) * 5)


def preset_values(entry: CatalogEntry, base: FilamentPreset, name: str) -> dict[str, Any]:
    """The user-preset JSON for an imported filament: the base's settings plus what the databases know."""
    values: dict[str, Any] = {
        "name": name,
        "from": "User",
        "inherits": base.name,
        "filament_settings_id": [name],
        "filament_vendor": [entry.brand or "Generic"],
        "version": PRESET_VERSION,
    }
    if entry.color:
        values["default_filament_colour"] = [entry.color]
    t = entry.temps
    nozzle = _mid(t.get("min_nozzle"), t.get("max_nozzle"))
    if nozzle:
        values["nozzle_temperature"] = [str(nozzle)]
        values["nozzle_temperature_initial_layer"] = [str(nozzle)]
        if t.get("min_nozzle"):
            values["nozzle_temperature_range_low"] = [str(int(t["min_nozzle"]))]
        if t.get("max_nozzle"):
            values["nozzle_temperature_range_high"] = [str(int(t["max_nozzle"]))]
    bed = _mid(t.get("min_bed"), t.get("max_bed"))
    if bed:
        for key in ("hot_plate_temp", "textured_plate_temp", "eng_plate_temp"):
            values[key] = [str(bed)]
            values[f"{key}_initial_layer"] = [str(bed)]
    if t.get("density"):
        values["filament_density"] = [f"{t['density']:g}"]
    if t.get("chamber"):
        values["chamber_temperature"] = [str(int(t["chamber"]))]
    sources = {SOURCE_CONNECT: "Prusa Connect", SOURCE_OFD: "Open Filament Database"}
    origin = sources.get(entry.source, entry.source)
    filled = "temperatures and density from " + origin if t else f"no print data in {origin}: settings are those of the base"
    values["filament_notes"] = f"Imported by the Prusa plugin from {origin}. Based on {base.name}; {filled}."
    return values


def sources_notice(connect_state: str, ofd_state: str, ofd_age_days: float | None = None) -> str:
    """What to tell the user about the catalogue's sources; "" when both are fine.

    States: "ok", "login" (Connect only: not logged in), "offline" (no answer), "cached" (OFD: using an older copy).
    Importing always works with what is available; only recording a material on the printer needs Connect.
    """
    parts: list[str] = []
    if connect_state == "login":
        parts.append("Log in to Prusa Connect (Settings) to also see Prusa's materials and record them on the printer.")
    elif connect_state == "offline":
        parts.append(
            "Prusa Connect is not answering: showing the Open Filament Database only. Recording a material on the printer needs Connect."
        )
    if ofd_state == "offline":
        parts.append("The Open Filament Database could not be reached and there is no saved copy: showing Prusa Connect only.")
    elif ofd_state == "cached" and ofd_age_days is not None and ofd_age_days >= 2:
        parts.append(f"Open Filament Database: using the copy from {int(ofd_age_days)} days ago (no connection).")
    if connect_state != "ok" and ofd_state == "offline":
        return "No filament database can be reached right now. Your existing filament presets still work; try again later."
    return " ".join(parts)


def preset_name(entry: CatalogEntry) -> str:
    """Name of the imported preset; Orca shows it in the Prepare tab's filament list."""
    return re.sub(r"[\\/:*?\"<>|]+", " ", entry.title).strip()
