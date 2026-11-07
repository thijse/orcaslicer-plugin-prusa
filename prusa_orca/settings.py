"""Plugin settings and secrets, kept in <data_dir>/orca_plugins/plugin_data/<key>/ (never in the repo)."""

from __future__ import annotations

import copy
import json
import os
import threading
from typing import Any

from .jsonview import obj

SETTINGS_FILE = "prusa_local.json"
TOKENS_FILE = "connect_tokens.json"

DEFAULTS: dict[str, Any] = {
    "prusalink": {"host": "", "username": "maker", "password": "", "api_key": ""},
    "connect": {"enabled": True, "printer_uuid": "", "api_key": ""},
    # model_id of the printer in Orca's Prusa vendor profile; Orca matches it against the printer preset.
    "printer": {"name": "Prusa XL", "model_id": "prusa_xl_5t_01"},
    "camera": {"rtsp_url": ""},
    "poll": {"status_seconds": 3.0, "tools_seconds": 30.0},
    # Off: a new load on the printer is offered for slicing. On: the slicer's slot follows it (see filament_watch).
    "filament": {"follow_printer": False},
    # Orca notifications per print event; see EVENT_TEXT in prusa_plugin.py.
    "notify": {
        "started": True,
        "first_layer": True,
        "near_end": True,
        "paused": True,
        "attention": True,
        "finished": True,
        "stopped": True,
        "failed": True,
    },
}


def default_data_dir() -> str:
    return os.path.join(
        os.path.expandvars(r"%APPDATA%") if os.name == "nt" else os.path.expanduser("~/.config"),
        "OrcaSlicer",
        "orca_plugins",
        "plugin_data",
        "prusa_plugin",
    )


def orca_data_dir(storage: str) -> str:
    """Orca's data dir: the parent of the orca_plugins folder that holds a plugin's storage folder."""
    path = os.path.normpath(storage)
    while True:
        parent = os.path.dirname(path)
        if os.path.basename(path) == "orca_plugins" or parent == path:
            return parent
        path = parent


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], obj(extra, key))
        else:
            out[key] = value
    return out


class Settings:
    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, SETTINGS_FILE)
        self.tokens_path = os.path.join(data_dir, TOKENS_FILE)
        self._lock = threading.Lock()
        self.values = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8-sig") as f:
                stored = obj(json.load(f))
        except (OSError, ValueError):
            stored = {}
        with self._lock:
            self.values = _deep_merge(DEFAULTS, stored)

    def save(self) -> None:
        with self._lock:
            os.makedirs(self.data_dir, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.values, f, indent=2)
            os.replace(tmp, self.path)

    def update(self, patch: dict[str, Any]) -> None:
        with self._lock:
            self.values = _deep_merge(self.values, patch)
        self.save()

    @property
    def lan_base_url(self) -> str:
        host = self.values["prusalink"].get("host", "").strip().rstrip("/")
        if not host:
            return ""
        return host if host.startswith(("http://", "https://")) else "http://" + host

    @property
    def lan_secret(self) -> str:
        link = self.values["prusalink"]
        return link.get("password") or link.get("api_key") or ""

    def public_view(self) -> dict[str, Any]:
        """Settings for the UI with secrets replaced by a set/unset flag."""
        view = copy.deepcopy(self.values)
        for section, key in (("prusalink", "password"), ("prusalink", "api_key"), ("connect", "api_key")):
            view[section][key] = bool(view[section].get(key))
        return view

    def fill_from_connect(self, detail: dict[str, Any]) -> list[str]:
        """Fill empty LAN fields from the Connect printer record; returns the names filled."""
        filled: list[str] = []
        link = self.values["prusalink"]
        connect = self.values["connect"]
        ip = obj(detail, "network_info").get("lan_ipv4", "")
        if ip and not link.get("host"):
            link["host"] = ip
            filled.append("PrusaLink host")
        key = detail.get("prusalink_api_key") or detail.get("api_key") or ""
        if key and not (link.get("password") or link.get("api_key")):
            link["api_key"] = key
            filled.append("PrusaLink key")
        if detail.get("prusaconnect_api_key") and not connect.get("api_key"):
            connect["api_key"] = detail["prusaconnect_api_key"]
            filled.append("Connect key")
        if filled:
            self.save()
        return filled
