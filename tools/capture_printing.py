"""Read-only capture of PrusaLink and Connect data during a print, saved under tests/fixtures/raw/printing/."""

from __future__ import annotations

import json
import os
import sys
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

from prusa_orca.backends.connect import CONNECT_BASE, ConnectBackend, TokenStore
from prusa_orca.backends.prusalink import PrusaLinkBackend
from prusa_orca.settings import Settings

DATA_DIR = os.path.expandvars(r"%APPDATA%\OrcaSlicer\orca_plugins\plugin_data\prusa_plugin")
OUT = os.path.join(_REPO_ROOT, "tests", "fixtures", "raw", "printing")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    settings = Settings(DATA_DIR)
    settings.load()
    link = settings.values["prusalink"]
    lan = PrusaLinkBackend(link["host"], settings.lan_secret, link.get("username", "maker"))
    stamp = time.strftime("%H%M%S")
    captured = {}
    for name, path in {"status": "/api/v1/status", "job": "/api/v1/job", "info": "/api/v1/info",
                       "legacy_job": "/api/job", "legacy_printer": "/api/printer"}.items():
        code, body = lan._get(path)
        captured[f"lan_{name}"] = {"http": code, "body": body}
    uuid = settings.values.get("connect", {}).get("printer_uuid", "")
    if uuid:
        cloud = ConnectBackend(TokenStore(settings.tokens_path), uuid)
        try:
            captured["connect_printer"] = cloud.fetch_printer()
        except Exception as exc:
            captured["connect_printer"] = {"error": str(exc)}
        for name, path in {"connect_jobs": f"/app/printers/{uuid}/jobs?limit=3",
                           "connect_queue": f"/app/printers/{uuid}/queue",
                           "connect_telemetry": f"/app/printers/{uuid}/telemetry?limit=5"}.items():
            try:
                captured[name] = cloud._request(CONNECT_BASE + path)
            except Exception as exc:
                captured[name] = {"error": str(exc)}
    path = os.path.join(OUT, f"capture_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(captured, f, indent=1, ensure_ascii=False)
    print(path)


if __name__ == "__main__":
    main()
