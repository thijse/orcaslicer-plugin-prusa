"""Read-only capture of Connect and PrusaLink responses into tests/fixtures/raw (gitignored)."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

DATA_DIR = os.path.expandvars(r"%APPDATA%\OrcaSlicer\orca_plugins\plugin_data\prusa")
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "fixtures", "raw")
UA = "PrusaSlicer/2.9.0"
# LAN calls must bypass the corporate PAC proxy, which answers 403 for the printer.
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def load(name: str) -> dict:
    with open(os.path.join(DATA_DIR, name), encoding="utf-8-sig") as f:
        return json.load(f)


def save(name: str, status: int, body: bytes) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        payload = json.loads(body) if body else None
    except ValueError:
        payload = body[:2000].decode("utf-8", "replace")
    with open(os.path.join(OUT_DIR, name + ".json"), "w", encoding="utf-8") as f:
        json.dump({"status": status, "body": payload}, f, indent=2)
    size = len(body) if body else 0
    print(f"{name:32s} {status} {size} bytes")


def get(opener, url: str, headers: dict) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **headers})
    try:
        with opener.open(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, str(exc).encode()


def connect(uuid: str) -> None:
    token = load("connect_tokens.json")["access_token"]
    auth = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base = "https://connect.prusa3d.com"
    for name, path in [
        ("connect_printers", "/app/printers"),
        ("connect_printer", f"/app/printers/{uuid}"),
        ("connect_supported_commands", f"/app/printers/{uuid}/supported-commands"),
        ("connect_queue", f"/app/printers/{uuid}/queue"),
        ("connect_jobs", f"/app/printers/{uuid}/jobs?limit=5"),
        ("connect_storages", f"/app/printers/{uuid}/storages"),
        ("connect_cameras", f"/app/printers/{uuid}/cameras"),
    ]:
        save(name, *get(urllib.request.build_opener(), base + path, auth))


def lan(cfg: dict, only: set[str] | None = None) -> None:
    host = cfg["host"]
    base = f"http://{host}"
    pw = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    pw.add_password(None, base, cfg.get("username") or "maker", cfg["password"])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPDigestAuthHandler(pw))
    for name, path in [
        ("lan_version", "/api/version"),
        ("lan_info", "/api/v1/info"),
        ("lan_status", "/api/v1/status"),
        ("lan_job", "/api/v1/job"),
        ("lan_storage", "/api/v1/storage"),
        ("lan_legacy_printer", "/api/printer"),
        ("lan_cameras", "/api/v1/cameras"),
    ]:
        if only and name not in only:
            continue
        save(name, *get(opener, base + path, {"Accept": "application/json"}))
        time.sleep(1.0)
    key = cfg.get("api_key")
    if key:
        save("lan_status_apikey", *get(DIRECT, base + "/api/v1/status", {"X-Api-Key": key}))


if __name__ == "__main__":
    local = load("prusa_local.json")
    which = sys.argv[1:] or ["connect", "lan"]
    if "connect" in which:
        connect(local["connect"]["printer_uuid"])
    if "lan" in which:
        lan(local["prusalink"], {n for n in which if n.startswith("lan_")} or None)
