"""Filament catalogue: search Prusa Connect and the Open Filament Database, import a filament, use it for slicing."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Mapping
from typing import Any, ClassVar

from ... import catalog
from ...backends.ofd import OfdCache
from ...catalog import CatalogEntry
from ...material_swap import PlannedSwap, compatible_types, printer_type, type_change
from ...materials import FilamentPreset
from ...model import ToolState
from ..host import LOG, orca
from ..orca_state import collect_base_presets, collect_filament_presets, local_bundle_dir
from .base import TabHandler

BUNDLE_ID = "prusa_plugin_filaments"
BUNDLE_NAME = "Imported filaments (Prusa plugin)"

_OFD: list[CatalogEntry] | None = None
_OFD_STATE = "offline"
_OFD_AGE: float | None = None
_OFD_LOCK = threading.Lock()


def _ofd(data_dir: str) -> tuple[list[CatalogEntry], str, float | None]:
    """OFD entries, loaded once per session (from the daily cache, downloading when it's old)."""
    global _OFD, _OFD_STATE, _OFD_AGE
    with _OFD_LOCK:
        if _OFD is None:
            cache = OfdCache(data_dir)
            dump, _OFD_STATE = cache.load()
            age = cache.age_seconds()
            _OFD_AGE = age / 86400 if age is not None else None
            _OFD = catalog.ofd_entries(dump)
            LOG.info("filament catalogue: %d OFD entries (%s)", len(_OFD), _OFD_STATE)
        return _OFD, _OFD_STATE, _OFD_AGE


class Recent:
    """Filaments the user picked, newest first, kept across sessions in recent_filaments.json."""

    def __init__(self, data_dir: str) -> None:
        self.path = os.path.join(data_dir, "recent_filaments.json")
        self._lock = threading.Lock()
        self._last_slots: list[str] = []

    def load(self) -> list[CatalogEntry]:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        items = data if isinstance(data, list) else []
        return [e for d in items if isinstance(d, dict) and (e := CatalogEntry.from_json(d)) is not None]

    def add(self, entry: CatalogEntry, tool: int = 0) -> None:
        with self._lock:
            _write_json(self.path, [e.to_json() for e in catalog.remember(self.load(), entry, tool)])

    def note_slots(self, slots: list[str], presets: list[FilamentPreset]) -> None:
        """Record the presets chosen in Orca's filament slots; slot N is tool N. Only changes are written."""
        if slots == self._last_slots:
            return
        self._last_slots = list(slots)
        by_name = {e.key: e for e in catalog.orca_entries(presets)}
        with self._lock:
            recent = self.load()
            changed = False
            for number, name in reversed(list(enumerate(slots, start=1))):
                entry = by_name.get(name)
                old = next((e for e in recent if e.id == entry.id), None) if entry else None
                if entry is not None and (old is None or number not in old.tools):
                    recent = catalog.remember(recent, entry, number)
                    changed = True
            if changed:
                _write_json(self.path, [e.to_json() for e in recent])


_RECENT: Recent | None = None


def recent(data_dir: str) -> Recent:
    global _RECENT
    if _RECENT is None or _RECENT.path != os.path.join(data_dir, "recent_filaments.json"):
        _RECENT = Recent(data_dir)
    return _RECENT


def _nozzle(tool: ToolState | None) -> catalog.Nozzle | None:
    return catalog.Nozzle(tool.nozzle_diameter, tool.hardened, tool.high_flow) if tool else None


class CatalogTab(TabHandler):
    COMMANDS: ClassVar[Mapping[str, str]] = {
        "catalog_search": "search",
        "catalog_use": "use",
        "cancel_swap": "cancel_swap",
    }

    def cancel_swap(self, message: dict[str, Any]) -> None:
        tool_number = int(message.get("tool") or 0)
        if self.rt.cancel_swap(tool_number):
            self.page.say(f"T{tool_number}: filament change cancelled; the printer's record stays as it is.")
        self.page.push()

    def __init__(self, page: Any) -> None:
        super().__init__(page)
        self._results: dict[str, CatalogEntry] = {}
        self._stale = False  # an import added a preset rt.presets doesn't list yet
        self._search_seq = 0

    def _tool(self, number: int) -> ToolState | None:
        snapshot = self.rt.snapshot
        return next((t for t in (snapshot.tools if snapshot else []) if t.tool_number == number), None)

    def search(self, message: dict[str, Any]) -> None:
        """Without a query: the recently used filaments. With one: Orca's presets, Connect and OFD, consolidated.

        With a tool, filaments its nozzle can't print are left out unless the user turns the filter off.
        """
        query = str(message.get("query") or "").strip()
        material = str(message.get("material") or "")
        brand = str(message.get("brand") or "")
        color = str(message.get("color") or "")
        finish = str(message.get("finish") or "")
        filtered = bool(query or brand or color or finish or material)
        tool_number = int(message.get("tool") or 0)
        tool = self._tool(tool_number)
        tool_nozzle = _nozzle(tool)
        nozzle = tool_nozzle if message.get("fit", True) else None
        loaded = tool.material if tool is not None and tool.is_loaded else ""
        same_material = loaded if message.get("same") else ""
        rt = self.rt
        if self._stale:
            self._stale = False
            rt.presets = collect_filament_presets()
        orca_entries = catalog.orca_entries(rt.presets)
        self._search_seq += 1
        seq = self._search_seq

        def work() -> None:
            recent_list = recent(rt.settings.data_dir).load()
            notice = ""
            ofd, ofd_state, ofd_age = _ofd(rt.settings.data_dir)
            filters = {"brand": brand, "material": material, "color": color, "finish": finish}
            if filtered:
                connect: list[CatalogEntry] = []
                backend = rt.backend
                cloud = backend.cloud if backend else None
                # Connect's search needs text; a brand or material filter alone stands in for it.
                connect_text = query or brand or material
                if not rt.tokens.logged_in or cloud is None:
                    connect_state = "login"
                elif not connect_text:
                    connect_state = "ok"
                else:
                    try:
                        nodes = cloud.catalog_materials(connect_text, first=100)
                        connect = [e for n in nodes if (e := catalog.connect_entry(n))]
                        connect_state = "ok"
                    except Exception as exc:
                        LOG.warning("Connect material search failed: %s", exc)
                        connect_state = "offline"
                merged = catalog.merge(connect, catalog.search(ofd, query, limit=600, **filters))
                found = catalog.search(orca_entries, query, limit=40, **filters)
                found += catalog.search(merged, query, limit=150, **filters)
                found = catalog.drop_imported(found, orca_entries)
                notice = catalog.sources_notice(connect_state, ofd_state, ofd_age)
            else:
                found = list(recent_list)
            hidden = 0
            if nozzle is not None:
                fits = [e for e in found if not catalog.misfit(e, nozzle)]
                hidden, found = len(found) - len(fits), fits
            if same_material:
                same = [e for e in found if not type_change(same_material, e.type)]
                hidden, found = hidden + len(found) - len(same), same
            if filtered:
                ids = {e.id for e in found}
                # Recently used matches first, grouped like the recent list; the rest by brand.
                groups = [(g, e) for g, e in catalog.recent_groups(recent_list, tool_number) if e.id in ids]
                listed = {e.id for _, e in groups}
                rows = groups + [("", e) for e in found if e.id not in listed]
            else:
                rows = catalog.recent_groups(found, tool_number)
            rows = rows[:100]
            if seq != self._search_seq:
                return  # a newer search replaced this one
            self._results = {e.id: e for _, e in rows}
            self.page.post_message(
                {
                    "type": "catalog",
                    "query": query,
                    "tool": tool_number,
                    "recent": not filtered,
                    "brands": catalog.brand_names(ofd, orca_entries),
                    "hidden": hidden,
                    "nozzle": catalog.nozzle_note(f"T{tool_number}", tool_nozzle) if tool_nozzle else "",
                    "loaded": printer_type(loaded),
                    "same_types": compatible_types(loaded),
                    "results": [e.view(group) for group, e in rows],
                    "notice": notice,
                }
            )

        self.page.in_background(work, "Searching filaments" if query else "")

    def use(self, message: dict[str, Any]) -> None:
        """Use a filament: import it as an Orca preset when it isn't one, then set it on the tool's slot for slicing
        and record it on the tool in Prusa Connect when Connect knows it. Without a tool, only imports."""
        # UI thread: read the presets, the tool and the bundle folder here; the rest goes to a worker.
        entry = self._results.get(str(message.get("key") or ""))
        if entry is None:
            self.page.say("Search again: that result is no longer listed.")
            return
        tool_number = int(message.get("tool") or 0)
        tool = self._tool(tool_number)
        rt, say = self.rt, self.page.say
        # "": not asked yet; "swap": unload and load it now; "orca": slice with it, leave the printer as it is.
        mode = str(message.get("mode") or "")
        new_type = printer_type(entry.type)
        if tool_number and tool is not None and tool.is_loaded and type_change(tool.material, entry.type) and not mode:
            printing = bool(rt.snapshot and rt.snapshot.raw_state in ("PRINTING", "PAUSED", "ATTENTION"))
            self.page.post_message(
                {
                    "type": "material_change",
                    "key": entry.id,
                    "tool": tool_number,
                    "loaded": printer_type(tool.material),
                    "loaded_name": " ".join(x for x in (tool.vendor, tool.name) if x) or tool.material,
                    "chosen": new_type,
                    "chosen_name": entry.title,
                    "can_swap": rt.tokens.logged_in and not printing,
                    "printing": printing,
                }
            )
            return
        if entry.source == catalog.SOURCE_ORCA:
            preset_name, write = entry.key, None
        else:
            base, why = catalog.pick_base(entry, collect_base_presets())
            if base is None:
                say(f"Can't use {entry.title}: {why}.")
                return
            name = catalog.preset_name(entry)
            preset_name = f"_local/{BUNDLE_ID}/{name}"  # how Orca names a local bundle's preset
            folder = local_bundle_dir(BUNDLE_ID)
            values = catalog.preset_values(entry, base, name)
            write = (folder, name, values, base.name)

        def work() -> None:
            notes: list[str] = []
            if write is not None:
                folder, name, values, base_name = write
                write_preset(folder, name, values)
                orca.host.preset.bundles.reload_local(BUNDLE_ID)
                if not entry.temps:
                    notes.append(f"No print data for it: it prints like {base_name} until you tune it.")
            recent(rt.settings.data_dir).add(entry, tool_number)
            if not tool_number:
                say(" ".join([f"Added {entry.title} to the slicer's filament list.", *notes]))
                return
            tx = orca.host.preset.filament.begin_update(slot_number=tool_number, preset_name=preset_name)
            try:
                tx.commit()
            except Exception:
                LOG.debug("empty filament commit", exc_info=True)
            done = [f"T{tool_number} slices with {entry.title}."]
            if mode == "swap":
                rt.plan_swap(PlannedSwap(tool_number, new_type, entry.brand or "Generic", entry.name, entry.color, entry.title))
                if tool is not None and tool.is_loaded:
                    cloud = rt.backend.cloud if rt.backend else None
                    if cloud is None:
                        raise RuntimeError("log in to Prusa Connect to unload remotely")
                    cloud.command("UNLOAD_FILAMENT", tool=tool_number)
                    rt.refresh_now()
                    done.append(
                        f"Unloading {printer_type(tool.material)} from T{tool_number}: remove the filament when the printer asks."
                    )
                done.append(
                    f"Then load {new_type} on T{tool_number} from the printer's menu (Filament > Load); "
                    f"{entry.title} is recorded in Prusa Connect as soon as the printer reports {new_type}."
                )
            elif mode == "orca":
                done.append(
                    f"The printer still has {printer_type(tool.material) if tool else 'its filament'} on T{tool_number}: load {new_type} before printing."
                )
            elif tool is not None and tool.is_loaded and rt.tokens.logged_in:
                try:
                    vendor = entry.brand or "Generic"
                    assigned = rt.assign_tool_material(
                        tool.index, vendor, entry.name, catalog.base_material(entry.type).upper(), entry.color
                    )
                    done.append(f"Recorded {assigned} on the tool in Prusa Connect.")
                except Exception as exc:
                    LOG.info("could not record %s on T%d: %s", entry.title, tool_number, exc)
                    done.append(f"Not recorded in Prusa Connect ({exc}).")
            say(" ".join(done + notes))

        label = f"T{tool_number}: {entry.title}" if tool_number else f"Adding {entry.title}"
        self.page.in_background(work, label, kind="command", resource="catalog-import")
        self._stale = write is not None


def write_preset(folder: str, name: str, values: dict[str, Any]) -> None:
    """Write one filament preset into the local bundle, creating the bundle on first use."""
    os.makedirs(os.path.join(folder, "filament"), exist_ok=True)
    meta_path = os.path.join(folder, "bundle_metadata.json")
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    now = int(time.time())
    meta.update(
        {
            "id": BUNDLE_ID,
            "name": BUNDLE_NAME,
            "version": "1",
            "description": "Filaments imported from Prusa Connect and the Open Filament Database.",
            "author": "Prusa plugin",
            "updated_time": now,
        }
    )
    meta.setdefault("imported_time", now)
    _write_json(meta_path, meta)
    _write_json(os.path.join(folder, "filament", f"{name}.json"), values)


def _write_json(path: str, data: object) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    os.replace(tmp, path)
