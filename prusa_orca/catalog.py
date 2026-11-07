"""The filament catalogue: Prusa Connect and the Open Filament Database merged, and imported as Orca presets.

Pure logic; the backends fetch the data and the app writes the preset. Connect wins over OFD wherever both
have a value, and a Prusa printer's own Prusament profile wins over both.
"""

from __future__ import annotations

import colorsys
import difflib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any, cast

from .colors import COLOR_WORDS, FINISH_WORDS, FINISHES
from .jsonview import JsonObj, flag, number, obj, objs, text
from .material_swap import printer_type
from .materials import FilamentPreset

SOURCE_CONNECT = "connect"
SOURCE_OFD = "ofd"
SOURCE_ORCA = "orca"  # a filament preset Orca already has


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
    min_nozzle_diameter: float = 0.0
    sources: list[str] = field(default_factory=list)  # every database that has it, once merged
    tools: list[int] = field(default_factory=list)  # recent list only: tools it was used on

    @property
    def title(self) -> str:
        name = self.name
        if self.source != SOURCE_ORCA and self.brand and not _norm(name).startswith(_norm(self.brand)):
            name = f"{self.brand} {name}"
        return name

    @property
    def id(self) -> str:
        return f"{self.source}:{self.key}"

    def view(self, group: str = "") -> dict[str, Any]:
        return {
            "key": self.id,
            "group": group or brand_key(self.brand),
            "group_label": group or self.brand,
            "brand": self.brand,
            "name": self.name,
            "title": self.title,
            "type": self.type,
            "color": self.color,
            "source": self.source,
            "sources": self.sources or [self.source],
            "abrasive": is_abrasive(self),
            "high_flow": "high_flow" in self.tags,
            "has_data": bool(self.temps) or self.source == SOURCE_ORCA,
            "basic_color": basic_color(self),
            "finishes": finishes(self),
        }

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(data: dict[str, Any]) -> CatalogEntry | None:
        known = {f.name for f in fields(CatalogEntry)}
        try:
            return CatalogEntry(**{k: v for k, v in data.items() if k in known})
        except TypeError:
            return None


def _fold(value: str) -> str:
    """Lower case without accents: "Créme" -> "creme"."""
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _norm(value: str) -> str:
    # "+" stays: "PLA+" is a different product from "PLA".
    return re.sub(r"[^a-z0-9+]+", " ", _fold(value)).strip()


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
        traits = obj(v, "traits")
        out.append(
            CatalogEntry(
                brand=brand,
                name=f"{name} {colour}".strip() if colour and _norm(colour) not in _norm(name) else name,
                type=text(f, "material"),
                color=_hex(text(v, "color_hex")),
                source=SOURCE_OFD,
                key=text(v, "id"),
                tags=[t for t, on in traits.items() if on is True],
                temps=temps,
                url=text(f, "data_sheet_url"),
                min_nozzle_diameter=number(f, "min_nozzle_diameter"),
            )
        )
    return out


def orca_entries(presets: Iterable[FilamentPreset]) -> list[CatalogEntry]:
    """Orca's own filament presets for this printer, searchable next to the databases."""
    return [
        CatalogEntry(brand=p.vendor, name=_display_name(p.name), type=p.type, source=SOURCE_ORCA, key=p.name)
        for p in presets
        if p.compatible
    ]


def _display_name(preset: str) -> str:
    """ "_local/<bundle>/eSUN PLA+ Red" -> "eSUN PLA+ Red"; "Generic PLA @Prusa XL" -> "Generic PLA"."""
    return preset.rsplit("/", 1)[-1].split("@", 1)[0].strip()


def brand_names(*lists: Iterable[CatalogEntry]) -> list[str]:
    """One display name per brand (the most common spelling), Prusament first, then alphabetical."""
    spellings: dict[str, dict[str, int]] = {}
    for entries in lists:
        for e in entries:
            if e.brand:
                counts = spellings.setdefault(brand_key(e.brand), {})
                counts[e.brand] = counts.get(e.brand, 0) + 1
    names = [max(c.items(), key=lambda kv: kv[1])[0] for c in spellings.values()]
    return sorted(names, key=lambda n: (brand_key(n) != "prusament", _fold(n)))


def drop_imported(found: list[CatalogEntry], orca: list[CatalogEntry]) -> list[CatalogEntry]:
    """Database entries already imported as an Orca preset are listed once, as the Orca preset."""
    imported = {_fold(e.name) for e in orca}
    return [e for e in found if e.source == SOURCE_ORCA or _fold(preset_name(e)) not in imported]


# Suffixes brands carry in one database but not the other ("eSUN 3D" vs "eSUN").
_BRAND_NOISE = {"3d", "filament", "filaments", "official", "store", "lab"}


def brand_key(brand: str) -> str:
    """One key per brand across databases: "Bambu Lab" = "BambuLab", "eSUN 3D" = "eSUN"."""
    words = [w for w in _norm(brand).split() if w not in _BRAND_NOISE] or _norm(brand).split()
    joined = "".join(words)
    for noise in sorted(_BRAND_NOISE, key=len, reverse=True):
        if joined.endswith(noise) and len(joined) > len(noise) + 2:
            joined = joined[: -len(noise)]
    return joined


def base_material(material: str) -> str:
    """The material without a product-line suffix: Connect files "PLA+" under "PLA Pro", OFD under "PLA"."""
    first = _norm(material).split()
    return first[0].rstrip("+") if first else ""


# Spellings the two databases differ in; applied to joined words before splitting.
_SYNONYMS = (
    (r"\bcarbon ?fib(?:er|re)\b", "cf"),
    (r"\bglass ?fib(?:er|re)\b", "gf"),
    (r"\bgray\b", "grey"),
    (r"\bcolou?r\b", ""),
    (r"\bnfc\b", ""),
)


def _words(e: CatalogEntry) -> set[str]:
    """Name words for matching across databases.

    Folded to lower case without accents; RAL codes, the brand and the material words dropped; "PET-G" = "PETG",
    "PA6-CF20" = "PA6 CF20", "Gray" = "Grey", "Carbon Fiber" = "CF".
    """
    value = _fold(_clean(e.name))
    value = re.sub(r"\bral\s*\d{4}\b", " ", value)
    # Prusament's recycled line: "rPLA Corn" (Connect) = "PLA r Corn" (OFD).
    value = re.sub(r"\br(pla|petg)\b", r"\1 r", value)
    value = re.sub(r"\b([a-z]+)-([a-z])\b", r"\1\2", re.sub(r"\b([a-z])-([a-z]+)\b", r"\1\2", value))
    value = _norm(value)
    for pattern, repl in _SYNONYMS:
        value = re.sub(pattern, repl, value)
    noise = set(_norm(e.brand).split()) | {brand_key(e.brand)}
    # The material is compared separately; its words would only inflate the overlap.
    material = set(_norm(e.type).split()) | {base_material(e.type)}
    material |= {re.sub(r"(cf|gf)$", "", m) for m in material}
    return {w for w in value.split() if w not in noise and w not in material}


def _same_word(a: str, b: str) -> bool:
    """Equal, or one small typo apart ("briliant" ~ "brilliant"); never for numbers or short words."""
    if a == b:
        return True
    if min(len(a), len(b)) < 5 or any(c.isdigit() for c in a + b):
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.88


def _overlap(wa: set[str], wb: set[str]) -> float:
    """Jaccard overlap of two word sets, counting near-identical spellings as the same word."""
    rest = set(wb)
    shared = 0
    for w in sorted(wa):
        match = w if w in rest else next((x for x in sorted(rest) if _same_word(w, x)), None)
        if match is not None:
            rest.discard(match)
            shared += 1
    return shared / (len(wa) + len(wb) - shared)


def _rgb(color: str) -> tuple[int, int, int] | None:
    c = color.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)) if re.fullmatch(r"[0-9a-fA-F]{6}", c) else None


def _color_close(a: str, b: str) -> bool:
    x, y = _rgb(a), _rgb(b)
    return x is not None and y is not None and sum((p - q) ** 2 for p, q in zip(x, y, strict=True)) <= 60**2


# Share of name words two entries must have in common to be one product ("PETG Prusa Galaxy Black" ~ "PETG Galaxy Black").
SAME_PRODUCT = 0.75


def same_product(a: CatalogEntry, b: CatalogEntry) -> float:
    """How alike two entries are, 0..1; 0 for different brands or materials."""
    if brand_key(a.brand) != brand_key(b.brand):
        return 0.0
    ma, mb = base_material(a.type), base_material(b.type)
    if ma and mb and not (ma.startswith(mb) or mb.startswith(ma)):  # "petgcf" ~ "petg", "pla" !~ "petg"
        return 0.0
    wa, wb = _words(a), _words(b)
    if not wa and not wb:
        return 1.0 if not a.color or not b.color or _color_close(a.color, b.color) else 0.0
    if not wa or not wb:
        return 0.0
    score = _overlap(wa, wb)
    # One database leaves out a line name ("PolyLite ASA Army Brown" vs "ASA Army Brown"): a subset counts
    # when only one word is missing and the colours agree.
    small, big = sorted((wa, wb), key=len)
    # Words that name a different product, never a line name one database leaves out.
    distinct = {"lightweight", "lw", "glow", "matte", "metallic", "hs", "hf", "cf", "gf", "esd", "pro", "plus", "blend"}
    extra = big - {w for w in big if any(_same_word(w, s) for s in small)}
    if (
        len(big) - len(small) == 1
        and len(small) >= 2
        and _overlap(small, small & big) == 1.0
        and not extra & distinct
        and _color_close(a.color, b.color)
    ):
        score = max(score, SAME_PRODUCT)
    return score


def merge(connect: Iterable[CatalogEntry], ofd: Iterable[CatalogEntry]) -> list[CatalogEntry]:
    """One list: Connect entries with gaps filled from the same product in OFD, then OFD entries Connect lacks.

    Names differ between the databases ("Easy PET-G" vs "Easy PETG", "Silk" left out), so a pair is one product
    when most name words agree; the best pairs go first and the colour breaks ties.
    """
    connect, ofd = list(connect), list(ofd)
    by_brand: dict[str, list[int]] = {}
    for j, o in enumerate(ofd):
        by_brand.setdefault(brand_key(o.brand), []).append(j)
    pairs: list[tuple[float, bool, int, int]] = []
    for i, c in enumerate(connect):
        for j in by_brand.get(brand_key(c.brand), []):
            score = same_product(c, ofd[j])
            if score >= SAME_PRODUCT:
                pairs.append((score, _color_close(c.color, ofd[j].color), i, j))
    pairs.sort(reverse=True)
    taken_c: set[int] = set()
    taken_o: set[int] = set()
    for _, _, i, j in pairs:
        if i in taken_c or j in taken_o:
            continue
        taken_c.add(i)
        taken_o.add(j)
        c, o = connect[i], ofd[j]
        c.temps = {**o.temps, **c.temps}
        c.color = c.color or o.color
        c.url = c.url or o.url
        c.tags = sorted(set(c.tags) | set(o.tags))
        c.min_nozzle_diameter = c.min_nozzle_diameter or o.min_nozzle_diameter
        c.sources = [SOURCE_CONNECT, SOURCE_OFD]
    return connect + [o for j, o in enumerate(ofd) if j not in taken_o]


@dataclass
class Nozzle:
    """What a tool's nozzle can print."""

    diameter: float = 0.4
    hardened: bool = False
    high_flow: bool = False


_ABRASIVE_TAGS = {"abrasive", "contains_carbon_fiber", "contains_glass_fiber", "contains_kevlar", "contains_metal"}


def is_abrasive(e: CatalogEntry) -> bool:
    if _ABRASIVE_TAGS & set(e.tags):
        return True
    words = set(_norm(f"{e.name} {e.type}").replace("-", " ").split())
    return bool(words & {"cf", "gf"}) or bool(re.search(r"(cf|gf)$", _norm(e.type).replace(" ", "")))


def misfit(e: CatalogEntry, nozzle: Nozzle) -> str:
    """Why a filament doesn't suit the nozzle, "" when it does."""
    if is_abrasive(e) and not nozzle.hardened:
        return "abrasive"
    if "high_flow" in e.tags and not nozzle.high_flow:
        return "high flow"
    if e.min_nozzle_diameter and nozzle.diameter + 1e-6 < e.min_nozzle_diameter:
        return f"needs a {e.min_nozzle_diameter:g} mm nozzle"
    return ""


def nozzle_note(label: str, nozzle: Nozzle) -> str:
    lines = [f"{label}'s nozzle: {nozzle.diameter:g} mm"]
    lines.append(
        "Hardened: abrasive filaments allowed" if nozzle.hardened else "Not hardened: no abrasive filaments (CF, GF, metal)"
    )
    lines.append("High flow: high-flow filaments allowed" if nozzle.high_flow else "Standard flow: no high-flow filaments")
    return "\n".join(lines)


RECENT_LIMIT = 30


def remember(recent: list[CatalogEntry], entry: CatalogEntry, tool: int = 0) -> list[CatalogEntry]:
    """The recently-used list with `entry` first, used on `tool` (1-based) as well as on its earlier tools."""
    old = next((e for e in recent if e.id == entry.id), None)
    tools = [tool] if tool else []
    tools += [t for t in (old.tools if old else []) if t != tool]
    entry = replace(entry, tools=tools)
    return [entry, *[e for e in recent if e.id != entry.id]][:RECENT_LIMIT]


def recent_groups(recent: list[CatalogEntry], tool: int) -> list[tuple[str, CatalogEntry]]:
    """The recent list for the finder: this tool's filaments first, then all of them; each listed once."""
    mine = [e for e in recent if tool in e.tools] if tool else []
    seen = {e.id for e in mine}
    return [(f"Recent for T{tool}", e) for e in mine] + [("All recent", e) for e in recent if e.id not in seen]


def _hue(color: str) -> str:
    """The basic colour of a colour code, for names without a colour word."""
    rgb = _rgb(color)
    if rgb is None:
        return ""
    h, light, sat = colorsys.rgb_to_hls(*(v / 255 for v in rgb))
    if light > 0.9:
        return "white"
    if light < 0.12:
        return "black"
    if sat < 0.15:
        return "grey"
    deg = h * 360
    if sat < 0.45 and 20 <= deg < 50 and light > 0.6:
        return "beige"
    if 15 <= deg < 45 and light < 0.45:
        return "brown"
    for limit, name in (
        (15, "red"),
        (45, "orange"),
        (70, "yellow"),
        (165, "green"),
        (255, "blue"),
        (290, "purple"),
        (335, "pink"),
    ):
        if deg < limit:
            return name
    return "red"


def basic_color(e: CatalogEntry) -> str:
    """One of colors.BASIC_COLORS: the last colour word in the name ("Grey Green" -> green), else the colour code."""
    named = [COLOR_WORDS[w] for w in _norm(e.name).split() if w in COLOR_WORDS]
    return named[-1] if named else _hue(e.color)


def finishes(e: CatalogEntry) -> list[str]:
    """The finishes (colors.FINISHES) the name or the database's tags name."""
    found = {FINISH_WORDS[w] for w in _norm(e.name).split() if w in FINISH_WORDS}
    found |= {t for t in e.tags if t in FINISHES}
    return sorted(found)


def search(
    entries: Iterable[CatalogEntry],
    query: str = "",
    brand: str = "",
    material: str = "",
    limit: int = 60,
    color: str = "",
    finish: str = "",
) -> list[CatalogEntry]:
    """Entries whose words all appear in brand+name+type, Prusament first, then by brand and name.

    `material` matches by the printer's type ("PETG" also finds PCTG). `color` is a basic colour, or "unknown" for
    entries without one; `finish` a finish, or "none" for entries without any.
    """
    words = _norm(query).split()
    want_brand, want_type = brand_key(brand) if brand else "", printer_type(material)
    hits: list[CatalogEntry] = []
    for e in entries:
        hay = f"{_norm(e.brand)} {_norm(e.name)} {_norm(e.type)}".split()
        if want_brand and brand_key(e.brand) != want_brand:
            continue
        if want_type and printer_type(e.type) != want_type:
            continue
        if color and color != (basic_color(e) or "unknown"):
            continue
        if finish and finish not in (finishes(e) or ["none"]):
            continue
        if all(any(h.startswith(w) for h in hay) for w in words):
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
