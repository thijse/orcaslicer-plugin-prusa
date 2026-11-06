"""Reading Orca's presets and project (UI thread only)."""

from __future__ import annotations

import os
import urllib.parse
from typing import Any

from .. import filament_sync
from ..materials import FilamentIdResolver, FilamentPreset
from ..settings import Settings, default_data_dir, orca_data_dir
from .host import orca


def _configured_settings() -> Settings:
    try:
        return Settings(orca.host.plugin.storage() if orca is not None else default_data_dir())
    except Exception:
        return Settings(default_data_dir())


def _configured_hosts() -> list[str]:
    """The LAN hosts in the saved settings, as http:// URLs for request_permissions."""
    settings = _configured_settings()
    hosts = [settings.lan_base_url] if settings.lan_base_url else []
    camera = urllib.parse.urlsplit(settings.values["camera"].get("rtsp_url", "")).hostname
    if camera:
        hosts.append(f"http://{camera}")
    return hosts


_RESOLVER: FilamentIdResolver | None = None


def _id_resolver() -> FilamentIdResolver | None:
    global _RESOLVER
    if _RESOLVER is None:
        # storage() is under <data_dir>/orca_plugins/plugin_data/ (deeper for a cloud install); system profiles live in <data_dir>/system.
        _RESOLVER = FilamentIdResolver(os.path.join(orca_data_dir(orca.host.plugin.storage()), "system"))
    return _RESOLVER


def _first(preset: Any, key: str) -> str:
    """First value of a preset option, as Orca's per-extruder options are lists or ';'-joined strings."""
    value = preset.config_value(key)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").split(";")[0].strip('"')


def collect_filament_presets() -> list[FilamentPreset]:
    """UI thread only: filament presets for the current printer, with filament_id where Orca exposes it."""
    out: list[FilamentPreset] = []
    bundle = orca.host.preset_bundle()
    filaments = bundle.filaments
    resolver = _id_resolver()
    for name in filaments.preset_names():
        preset = filaments.find_preset(name)
        if preset is None or preset.is_default or not preset.is_visible:
            continue
        filament_id = _first(preset, "filament_id") or (resolver.resolve(preset.file) if resolver and preset.file else "")
        out.append(
            FilamentPreset(
                name=preset.name,
                filament_id=filament_id,
                vendor=_first(preset, "filament_vendor"),
                type=_first(preset, "filament_type"),
                compatible=bool(preset.is_compatible),
            )
        )
    return out


def collect_base_presets() -> list[FilamentPreset]:
    """UI thread only: system filament presets compatible with the printer, visible or not, as import bases."""
    out: list[FilamentPreset] = []
    filaments = orca.host.preset_bundle().filaments
    for name in filaments.preset_names():
        preset = filaments.find_preset(name)
        if preset is None or preset.is_default or not preset.is_system or not preset.is_compatible:
            continue
        out.append(
            FilamentPreset(name=preset.name, vendor=_first(preset, "filament_vendor"), type=_first(preset, "filament_type"))
        )
    return out


def local_bundle_dir(bundle_id: str) -> str:
    """UI thread only: <data_dir>/user/<preset folder>/_local/<bundle_id>, where Orca loads a local bundle from."""
    data_dir = orca_data_dir(orca.host.plugin.storage())
    return os.path.join(data_dir, "user", _active_preset_folder(data_dir), "_local", bundle_id)


def _active_preset_folder(data_dir: str) -> str:
    """The user preset folder in use: read from where a loaded user preset lives (OrcaSlicer.conf is off limits)."""
    user_root = os.path.normcase(os.path.join(data_dir, "user")) + os.sep
    filaments = orca.host.preset_bundle().filaments
    for name in filaments.preset_names():
        preset = filaments.find_preset(name)
        path = os.path.normcase(str(getattr(preset, "file", "") or ""))
        if preset is not None and preset.is_user() and path.startswith(user_root):
            return path[len(user_root) :].split(os.sep, 1)[0]
    return "default"


def _project_path() -> str:
    try:
        return str(orca.host.plater().project_path() or "")
    except Exception:
        return ""


def _preset_names() -> dict[str, Any]:
    try:
        bundle = orca.host.preset_bundle()
        return {
            "printer": bundle.current_printer_preset().name,
            "process": str(bundle.full_config_value("print_settings_id") or ""),
            "filaments": list(bundle.current_filament_preset_names()),
        }
    except Exception:
        return {}


def printer_preset_nozzles() -> tuple[str, Any, Any]:
    """UI thread only: name, nozzle_diameter and nozzle_type of the printer preset being edited."""
    preset = orca.host.preset_bundle().current_printer_preset()
    return preset.name, preset.config_value("nozzle_diameter"), preset.config_value("nozzle_type")


def printer_preset_model() -> tuple[str, str]:
    """UI thread only: name and printer_model of the selected printer preset."""
    preset = orca.host.preset_bundle().current_printer_preset()
    return preset.name, str(preset.config_value("printer_model") or "")


def filament_slots() -> tuple[list[str], list[str]]:
    """UI thread only: preset name and colour of each Orca filament slot."""
    bundle = orca.host.preset_bundle()
    return list(bundle.current_filament_preset_names()), filament_sync.parse_colours(bundle.full_config_value("filament_colour"))
