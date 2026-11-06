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


class CatalogTab(TabHandler):
    COMMANDS: ClassVar[Mapping[str, str]] = {
        "catalog_search": "search",
        "catalog_import": "import_filament",
    }

    def __init__(self, page: Any) -> None:
        super().__init__(page)
        self._results: dict[str, CatalogEntry] = {}

    def search(self, message: dict[str, Any]) -> None:
        query = str(message.get("query") or "").strip()
        material = str(message.get("material") or "")
        rt = self.rt

        def work() -> None:
            ofd, ofd_state, ofd_age = _ofd(rt.settings.data_dir)
            connect: list[CatalogEntry] = []
            backend = rt.backend
            cloud = backend.cloud if backend else None
            if not rt.tokens.logged_in or cloud is None:
                connect_state = "login"
            else:
                try:
                    nodes = cloud.catalog_materials(query, first=80) if query else []
                    connect = [e for n in nodes if (e := catalog.connect_entry(n)) is not None]
                    connect_state = "ok"
                except Exception as exc:
                    LOG.warning("Connect material search failed: %s", exc)
                    connect_state = "offline"
            merged = catalog.merge(connect, catalog.search(ofd, query, material=material, limit=400))
            hits = catalog.search(merged, query, material=material, limit=80)
            self._results = {f"{e.source}:{e.key}": e for e in hits}
            self.page.post_message(
                {
                    "type": "catalog",
                    "query": query,
                    "results": [e.view() for e in hits],
                    "notice": catalog.sources_notice(connect_state, ofd_state, ofd_age),
                }
            )

        self.page.in_background(work, "Searching filaments" if query else "", resource="catalog")

    def import_filament(self, message: dict[str, Any]) -> None:
        # UI thread: read the presets and the bundle folder here; writing and reloading go to a worker.
        entry = self._results.get(str(message.get("key") or ""))
        if entry is None:
            self.page.say("Search again: that result is no longer listed.")
            return
        slot = int(message.get("slot") or 0)
        base, why = catalog.pick_base(entry, collect_base_presets())
        if base is None:
            self.page.say(f"Can't import {entry.title}: {why}.")
            return
        name = catalog.preset_name(entry)
        full_name = f"_local/{BUNDLE_ID}/{name}"  # how Orca names a local bundle's preset
        existing = {p.name for p in collect_filament_presets()}
        folder = local_bundle_dir(BUNDLE_ID)
        say = self.page.say

        def work() -> None:
            write_preset(folder, name, catalog.preset_values(entry, base, name))
            orca.host.preset.bundles.reload_local(BUNDLE_ID)
            self.rt.presets = []  # re-read on the next page init
            did = "Updated" if full_name in existing else "Imported"
            data = "" if entry.temps else f" No print data for it: it prints like {base.name} until you tune it."
            if slot:
                tx = orca.host.preset.filament.begin_update(slot_number=slot, preset_name=full_name)
                try:
                    tx.commit()
                except Exception:
                    LOG.debug("empty filament commit", exc_info=True)
                say(f"{did} {name} and set it on filament {slot} for slicing.{data}")
            else:
                say(f"{did} {name}: pick it in the Prepare tab's filament list.{data}")

        self.page.in_background(work, f"Importing {entry.title}", kind="command", resource="catalog-import")


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
