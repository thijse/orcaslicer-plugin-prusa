"""PrusaLink (printer LAN API) client: status, uploads and job control."""

from __future__ import annotations

import http.client
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from typing import Any, Callable, Optional

from ..model import JobState, PrinterTelemetry, RawPrinterState
from ..phase import interpret_phase

LOG = logging.getLogger("prusa_orca.backends.prusalink")


def parse_status(status: dict[str, Any], host: str = "") -> PrinterTelemetry:
    printer = status.get("printer") or {}
    job = status.get("job") or {}
    storage = status.get("storage") or {}
    try:
        raw_state = RawPrinterState(str(printer.get("state", "UNKNOWN")).upper())
    except ValueError:
        raw_state = RawPrinterState.UNKNOWN
    telemetry = PrinterTelemetry(
        connected=True,
        raw_state=raw_state,
        ip_address=host,
        nozzle_temperature=float(printer.get("temp_nozzle") or 0.0),
        nozzle_target_temperature=float(printer.get("target_nozzle") or 0.0),
        bed_temperature=float(printer.get("temp_bed") or 0.0),
        bed_target_temperature=float(printer.get("target_bed") or 0.0),
        flow_percent=int(printer.get("flow") or 100),
        fan_print_rpm=int(printer.get("fan_print") or 0),
        fan_hotend_rpm=int(printer.get("fan_hotend") or 0),
        speed_percent=int(printer.get("speed") or 100),
        axis_x=printer.get("axis_x"),
        axis_y=printer.get("axis_y"),
        axis_z=printer.get("axis_z"),
        storage_available=bool(storage) and not storage.get("read_only", False),
        last_updated=time.time(),
        source="lan",
    )
    if job:
        telemetry.job = JobState(
            job_id=job.get("id"),
            state=raw_state,
            progress_percent=float(job.get("progress") or 0.0),
            time_remaining_seconds=int(job.get("time_remaining") or 0),
            time_printing_seconds=int(job.get("time_printing") or 0),
        )
    telemetry.interpreted_phase = interpret_phase(telemetry)
    return telemetry


def apply_job_detail(telemetry: PrinterTelemetry, job: dict[str, Any]) -> None:
    file = job.get("file") or {}
    telemetry.job.file_name = str(file.get("name") or "")
    telemetry.job.display_name = str(file.get("display_name") or telemetry.job.file_name)


def extract_plate_gcode(path: str, plate_index: int, out_dir: str) -> str:
    """G-code of one plate from Orca's sliced .gcode.3mf (Metadata/plate_N.gcode); a plain G-code path passes through."""
    if not zipfile.is_zipfile(path):
        return path
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if re.fullmatch(r"Metadata/plate_\d+\.gcode", n)]
        wanted = f"Metadata/plate_{max(plate_index, 1)}.gcode"
        name = wanted if wanted in names else (names[0] if len(names) == 1 else "")
        if not name:
            raise ValueError(f"no G-code for plate {plate_index} in {os.path.basename(path)}")
        target = os.path.join(out_dir, f"plate_{max(plate_index, 1)}.gcode")
        with archive.open(name) as src, open(target, "wb") as dst:
            while chunk := src.read(1 << 20):
                dst.write(chunk)
    return target


def printer_file_name(project_name: str, plate_index: int) -> str:
    """An 8.3-safe-ish, unique-enough file name for the printer's USB drive."""
    base = re.sub(r"\.gcode(\.3mf)?$|\.3mf$", "", project_name or "orca", flags=re.I)
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", base).strip("_.") or "orca"
    suffix = f"_plate{plate_index}" if plate_index > 1 else ""
    return f"{base[:60]}{suffix}.gcode"


class PrusaLinkBackend:
    def __init__(self, host: str, secret: str, username: str = "maker", timeout: float = 10.0) -> None:
        self.host = host.strip().split("://")[-1].split("/")[0]
        self.base_url = f"http://{self.host}"
        self.timeout = timeout
        self._secret = secret
        passwords = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        passwords.add_password(None, self.base_url, username or "maker", secret)
        # Never route LAN calls through a system/PAC proxy; corporate proxies answer 403 for private IPs.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                                   urllib.request.HTTPDigestAuthHandler(passwords))

    def _get(self, path: str) -> tuple[int, Any]:
        req = urllib.request.Request(self.base_url + path, headers={"Accept": "application/json"})
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            return exc.code, None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            LOG.debug("PrusaLink %s failed: %s", path, exc)
            return 0, None

    def fetch_bytes(self, path: str) -> Optional[bytes]:
        """Raw GET (e.g. /thumb/l/usb/<file>); None on any failure."""
        try:
            # Thumbnails answer 401 to Digest; the API key works.
            req = urllib.request.Request(self.base_url + path, headers={"X-Api-Key": self._secret})
            with self._opener.open(req, timeout=max(self.timeout, 20)) as resp:
                return resp.read() if resp.status == 200 else None
        except (urllib.error.URLError, TimeoutError, OSError):
            return None

    def fetch_status(self) -> Optional[PrinterTelemetry]:
        code, body = self._get("/api/v1/status")
        if code != 200 or not isinstance(body, dict):
            return None
        telemetry = parse_status(body, self.host)
        if body.get("job"):
            # /status names no file; /job does.
            code, job = self._get("/api/v1/job")
            if code == 200 and isinstance(job, dict):
                apply_job_detail(telemetry, job)
        return telemetry

    def fetch_info(self) -> Optional[dict[str, Any]]:
        code, body = self._get("/api/v1/info")
        return body if code == 200 else None

    def _send(self, method: str, path: str, headers: Optional[dict[str, str]] = None, data: Any = None,
              timeout: Optional[float] = None) -> int:
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers or {})
        try:
            with self._opener.open(req, timeout=timeout or self.timeout) as resp:
                resp.read()
                return resp.status
        except urllib.error.HTTPError as exc:
            LOG.warning("PrusaLink %s %s: HTTP %s %s", method, path, exc.code, exc.read()[:200])
            return exc.code

    def storage_path(self) -> str:
        code, body = self._get("/api/v1/storage")
        for storage in (body or {}).get("storage_list", []) if code == 200 else []:
            if storage.get("available") and not storage.get("read_only"):
                return storage.get("path", "/usb/").strip("/")
        return "usb"

    def upload(self, local_path: str, remote_name: str, print_after: bool,
               progress: Optional[Callable[[int], None]] = None, cancelled: Optional[Callable[[], bool]] = None) -> int:
        """PUT a G-code file to the printer's storage; returns the HTTP status (201 on success)."""
        storage = self.storage_path()
        size = os.path.getsize(local_path)
        # Buddy firmware 8.0.1 answers 500 to "Overwrite: ?1" when the file is "busy" (the printer keeps
        # the last uploaded file selected for printing), so never write over a file: use the first free name.
        stem, ext = os.path.splitext(remote_name)
        for n in range(100):
            name = remote_name if n == 0 else f"{stem}_{n}{ext}"
            path = f"/api/v1/files/{storage}/{urllib.parse.quote(name)}"
            if self._get(path)[0] == 404:
                break
        self.last_upload_name = name
        # Streamed with X-Api-Key in one request: a Digest challenge would make urllib send the body twice,
        # and the printer drops a PUT whose body arrives in small reads (HTTP 408).
        conn = http.client.HTTPConnection(self.host, timeout=max(120.0, size / 10_000))
        try:
            conn.putrequest("PUT", path)
            for key, value in {"X-Api-Key": self._secret, "Content-Type": "application/octet-stream",
                               "Content-Length": str(size), "Overwrite": "?0",
                               "Print-After-Upload": "?1" if print_after else "?0"}.items():
                conn.putheader(key, value)
            conn.endheaders()
            sent = 0
            # 64 kB writes made the Buddy firmware answer 500; 1 MB writes work.
            with open(local_path, "rb") as f:
                while chunk := f.read(1 << 20):
                    if cancelled and cancelled():
                        raise InterruptedError("upload cancelled")
                    conn.sock.sendall(chunk)
                    sent += len(chunk)
                    if progress and size:
                        progress(int(sent * 100 / size))
            resp = conn.getresponse()
            body = resp.read()
            if resp.status >= 300:
                LOG.warning("PrusaLink upload %s: HTTP %s %s", remote_name, resp.status, body[:200])
            return resp.status
        finally:
            conn.close()

    def list_files(self) -> list[dict[str, Any]]:
        """Print files on the printer's storage, newest first: name (8.3), display_name, m_timestamp."""
        code, body = self._get(f"/api/v1/files/{self.storage_path()}/")
        files = [f for f in (body or {}).get("children", []) if f.get("type") == "PRINT_FILE"] if code == 200 else []
        return sorted(files, key=lambda f: f.get("m_timestamp") or 0, reverse=True)

    def delete_file(self, name: str) -> int:
        """Delete a file from the printer's storage; 204 on success, 409 while it is selected for printing."""
        return self._send("DELETE", f"/api/v1/files/{self.storage_path()}/{urllib.parse.quote(name)}")

    def print_file(self, name: str) -> int:
        """Start printing a file already on the printer's storage; 204 on success, 409 when busy."""
        return self._send("POST", f"/api/v1/files/{self.storage_path()}/{urllib.parse.quote(name)}")

    def job_command(self, action: str) -> int:
        """pause, resume or stop the current job."""
        code, job = self._get("/api/v1/job")
        if code != 200 or not job:
            return 404
        if action == "stop":
            return self._send("DELETE", f"/api/v1/job/{job['id']}")
        return self._send("PUT", f"/api/v1/job/{job['id']}/{action}")
