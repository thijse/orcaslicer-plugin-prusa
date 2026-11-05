"""Prusa Connect cloud backend: OAuth2 PKCE tokens, printer detail and per-tool materials."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..model import JobState, PrinterTelemetry, RawPrinterState, ToolState
from ..phase import interpret_phase
from .connect_graphql import CAMERAS_BY_PRINTER, GRAPHQL_URL, PRINTER_FFF_TELEMETRY, UPDATE_PRINTER_MATERIAL, WAREHOUSE_MATERIALS

LOG = logging.getLogger("prusa_orca.backends.connect")

# PrusaSlicer's public OAuth client (src/slic3r-shared/.../ServiceConfig.cpp); personal use only.
CLIENT_ID = "oamhmhZez7opFosnwzElIgE2oGgI2iJORSkw587O"
REDIRECT_URI = "prusaslicer://login"
ACCOUNT_BASE = "https://account.prusa3d.com"
CONNECT_BASE = "https://connect.prusa3d.com"
# Connect omits tools.N.material and Cloudflare rejects urllib's default agent unless the client looks like a browser.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


class ConnectAuthError(Exception):
    pass


def generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


def build_authorize_url(challenge: str, language: str = "en") -> str:
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": "basic_info",
        "redirect_uri": REDIRECT_URI,
        "language": language,
    }
    return f"{ACCOUNT_BASE}/o/authorize/?{urllib.parse.urlencode(params)}&choose_account=1"


def code_from_redirect(text: str) -> str:
    """Accept a bare code or the full prusaslicer://login?code=... URL."""
    text = text.strip()
    if "code=" in text:
        text = urllib.parse.parse_qs(urllib.parse.urlsplit(text).query).get("code", [""])[0]
    return "".join(ch for ch in text if ch.isalnum())


class TokenStore:
    """Access/refresh tokens in a JSON file, refreshed shortly before expiry."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.access_token = ""
        self.refresh_token = ""
        self.expires_at = 0.0
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        self.access_token = data.get("access_token", "")
        self.refresh_token = data.get("refresh_token", "")
        self.expires_at = float(data.get("expires_at", 0.0))

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"access_token": self.access_token, "refresh_token": self.refresh_token, "expires_at": self.expires_at},
                f,
                indent=2,
            )
        os.replace(tmp, self.path)

    @property
    def logged_in(self) -> bool:
        return bool(self.refresh_token or self.access_token)

    def clear(self) -> None:
        with self._lock:
            self.access_token = self.refresh_token = ""
            self.expires_at = 0.0
            with contextlib.suppress(OSError):
                os.remove(self.path)

    def _token_request(self, fields: dict[str, str]) -> None:
        body = urllib.parse.urlencode({"client_id": CLIENT_ID, **fields}).encode()
        req = urllib.request.Request(
            f"{ACCOUNT_BASE}/o/token/",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise ConnectAuthError(f"token endpoint answered HTTP {exc.code}") from exc
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        self.expires_at = time.time() + float(data.get("expires_in", 3600))
        self._save()

    def exchange_code(self, code: str, verifier: str) -> None:
        with self._lock:
            self._token_request(
                {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI, "code_verifier": verifier}
            )

    def bearer(self) -> str:
        with self._lock:
            if self.access_token and time.time() < self.expires_at - 60:
                return self.access_token
            if not self.refresh_token:
                raise ConnectAuthError("not logged in to Prusa Connect")
            self._token_request({"grant_type": "refresh_token", "refresh_token": self.refresh_token})
            return self.access_token


def _rgba_to_hex(rgba: str | None) -> str:
    if not rgba or not rgba.startswith("#") or len(rgba) < 7:
        return ""
    return "#" + rgba[1:7].upper()


def parse_graphql_tools(data: dict[str, Any]) -> list[ToolState]:
    """Tools from GetPrinterFffTelemetry: toolheads, or the MMU's slots when it is enabled."""
    printer = (((data.get("data") or {}).get("printer") or {}).get("printer")) or {}
    fff = printer.get("fff") or {}
    raws = fff.get("tools") or []
    # Buddy firmware: heads are "<n>", MMU feeder slots "<head>.<slot>" (src/connect/tools.hpp).
    slots = [r for r in raws if "." in str(r.get("id", ""))] if fff.get("hasMmuEnabled") is not False else []
    heads = {str(r.get("id")): r for r in raws if "." not in str(r.get("id", ""))}
    tools: list[ToolState] = []
    for raw in slots or list(heads.values()) or raws:
        cid = str(raw.get("id", len(tools)))
        head = heads.get(cid.split(".")[0], raw) if slots else raw
        idx = int(cid.split(".")[-1]) if slots else int(cid)
        features = head.get("features") or raw.get("features") or {}
        telemetry = dict(head.get("telemetry") or {})
        if slots:
            # The slot feeding the head is the active one; temperatures belong to the head.
            telemetry["active"] = bool((raw.get("telemetry") or {}).get("active"))
        tool = ToolState(
            index=idx,
            tool_number=idx + 1,
            kind="slot" if slots else "head",
            connect_id=cid,
            nozzle_diameter=float(features.get("nozzleDiameter") or 0.4),
            high_flow=bool(features.get("nozzleHighFlow")),
            hardened=bool(features.get("nozzleHardened")),
            temperature=float(telemetry.get("temp") or 0.0),
            target_temperature=float(telemetry.get("targetTemp") or 0.0),
            is_active=bool(telemetry.get("active")),
            is_loaded=False,
            material="",
            color="",
        )
        instance = raw.get("materialPackageInstance") or {}
        material = ((instance.get("package") or {}).get("material")) or {}
        if instance.get("__typename") == "FFFToolMaterialPackageInstance" and material:
            props = material.get("properties") or {}
            tool.is_loaded = True
            tool.material = (material.get("type") or {}).get("abbreviation") or material.get("abbreviation") or ""
            tool.name = material.get("name") or ""
            tool.vendor = (material.get("brand") or {}).get("name") or ""
            tool.color = _rgba_to_hex((material.get("primaryColor") or {}).get("colorRgba"))
            tool.min_temp = int(props.get("minPrintTemperature") or tool.min_temp)
            tool.max_temp = int(props.get("maxPrintTemperature") or tool.max_temp)
        tools.append(tool)
    tools.sort(key=lambda t: t.index)
    return tools


class ConnectBackend:
    """Read-only Prusa Connect client."""

    def __init__(self, tokens: TokenStore, printer_uuid: str, timeout: float = 15.0) -> None:
        self.tokens = tokens
        self.printer_uuid = printer_uuid
        self.timeout = timeout
        self.organization_id = ""
        self.printer_detail: dict[str, Any] = {}
        self.command_args: dict[str, list[dict[str, Any]]] = {}
        self._layer_heights: dict[int, float] = {}

    # Set from the plugin settings' "debug" section to test slow or failing Connect behaviour.
    simulate_delay = 0.0
    simulate_down = False

    def _request(self, url: str, body: bytes | None = None) -> Any:
        if self.simulate_delay:
            time.sleep(min(self.simulate_delay, self.timeout))
            if self.simulate_delay >= self.timeout:
                raise TimeoutError("simulated: no answer")
        if self.simulate_down:
            raise urllib.error.URLError("simulated: Connect is down")
        headers = {"Authorization": f"Bearer {self.tokens.bearer()}", "User-Agent": USER_AGENT, "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())

    def supported_commands(self) -> dict[str, list[str]]:
        """Command name -> printer states it can run in, as the printer reports to Connect."""
        data = self._request(f"{CONNECT_BASE}/app/printers/{self.printer_uuid}/supported-commands")
        self.command_args = {
            c["command"]: [a for a in c.get("args") or [] if a.get("input", True)]
            for c in data.get("commands") or []
            if c.get("command")
        }
        return {c["command"]: list(c.get("executable_from_state") or []) for c in data.get("commands") or [] if c.get("command")}

    def command(self, name: str, **kwargs: Any) -> Any:
        """Run a printer command through Connect and wait for the printer's answer."""
        body = json.dumps({"command": name, "kwargs": kwargs}).encode()
        return self._request(f"{CONNECT_BASE}/app/printers/{self.printer_uuid}/commands/sync", body)

    def list_printers(self) -> list[dict[str, Any]]:
        data = self._request(f"{CONNECT_BASE}/app/printers?limit=100")
        return [
            {
                "uuid": p.get("uuid", ""),
                "name": p.get("name") or p.get("uuid", ""),
                "model": p.get("printer_type_name") or p.get("printer_model") or "",
            }
            for p in (data.get("printers") or [])
            if p.get("uuid")
        ]

    def fetch_printer(self) -> dict[str, Any]:
        self.printer_detail = self._request(f"{CONNECT_BASE}/app/printers/{self.printer_uuid}")
        self.organization_id = self.printer_detail.get("organization_id", "") or self.organization_id
        return self.printer_detail

    def _graphql(self, operation: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        if not self.organization_id:
            self.fetch_printer()
        payload = json.dumps(
            {"operationName": operation, "query": query, "variables": {"organizationId": self.organization_id, **variables}}
        ).encode()
        data = self._request(GRAPHQL_URL, payload)
        if data.get("errors"):
            raise RuntimeError("; ".join(str(e.get("message", e)) for e in data["errors"]))
        return data

    def fetch_tools(self) -> list[ToolState]:
        return parse_graphql_tools(
            self._graphql("GetPrinterFffTelemetry", PRINTER_FFF_TELEMETRY, {"printerId": self.printer_uuid})
        )

    def snapshot_url(self) -> str:
        payload = json.dumps(
            {"operationName": "CamerasByPrinter", "query": CAMERAS_BY_PRINTER, "variables": {"printerUuid": self.printer_uuid}}
        ).encode()
        data = self._request(GRAPHQL_URL, payload)
        cams = (((data.get("data") or {}).get("camera") or {}).get("camerasConnection") or {}).get("edges") or []
        return next((((e.get("node") or {}).get("snapshots") or {}).get("lastSnapshotUrl") or "" for e in cams), "")

    def list_cameras(self) -> list[dict[str, Any]]:
        return self._request(f"{CONNECT_BASE}/app/printers/{self.printer_uuid}/cameras").get("cameras") or []

    def fetch_snapshot(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.tokens.bearer()}", "User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def search_materials(self, text: str, material_type: str = "", first: int = 20) -> list[dict[str, Any]]:
        variables: dict[str, Any] = {"first": first, "search": text}
        if material_type:
            variables["materialType"] = [material_type]
        data = self._graphql("WarehouseMaterials", WAREHOUSE_MATERIALS, variables)
        return (((data.get("data") or {}).get("warehouse") or {}).get("materials") or {}).get("nodes") or []

    def assign_material(self, tool_id: str, item: dict[str, Any]) -> None:
        """Record a material-database entry on a tool ("0".. or MMU slot "0.n"), as Connect's Tools > Assign does."""
        material = item.get("material") or {}
        if item.get("isCustom"):
            ref = {
                "uuid": item["uuid"],
                "name": material.get("name"),
                "type": material.get("type"),
                "abbreviation": material.get("abbreviation"),
            }
            if (material.get("primaryColor") or {}).get("colorRgba"):
                ref["primaryColor"] = {"colorRgba": material["primaryColor"]["colorRgba"]}
            ref = {k: v for k, v in ref.items() if v is not None}
        else:
            ref = {"uuid": item["uuid"]}
        printer = {"fffTools": [{"id": str(tool_id), "materialPackageInstance": {"package": {"material": ref}}}]}
        data = self._graphql(
            "UpdatePrinterMaterial", UPDATE_PRINTER_MATERIAL, {"printerId": self.printer_uuid, "printer": printer}
        )
        result = ((data.get("data") or {}).get("printer") or {}).get("updatePrinter") or {}
        if result.get("__typename") == "ConnectError":
            raise RuntimeError(result.get("message") or "Connect refused the assignment")

    def fetch_telemetry(self) -> PrinterTelemetry:
        detail = self.fetch_printer()
        tools = self.fetch_tools()
        try:
            raw_state = RawPrinterState(str(detail.get("state", "UNKNOWN")).upper())
        except ValueError:
            raw_state = RawPrinterState.UNKNOWN
        temp = detail.get("temp") or {}
        active = next((t for t in tools if t.is_active), tools[0] if tools else None)
        network = detail.get("network_info") or {}
        telemetry = PrinterTelemetry(
            connected=True,
            raw_state=raw_state,
            model=detail.get("printer_type_name", "Original Prusa XL"),
            printer_type=str(detail.get("printer_type") or ""),
            mmu_enabled=any(t.kind == "slot" for t in tools),
            firmware_version=detail.get("firmware", ""),
            uuid=self.printer_uuid,
            serial_number=detail.get("sn", ""),
            ip_address=network.get("lan_ipv4", ""),
            hostname=network.get("hostname", ""),
            bed_temperature=float(temp.get("temp_bed") or 0.0),
            bed_target_temperature=float(temp.get("target_bed") or 0.0),
            nozzle_temperature=active.temperature if active else 0.0,
            nozzle_target_temperature=active.target_temperature if active else 0.0,
            speed_percent=int(detail.get("speed") or 100),
            axis_x=detail.get("axis_x"),
            axis_y=detail.get("axis_y"),
            axis_z=detail.get("axis_z"),
            tools=tools,
            active_tool=active.index if active else 0,
            last_updated=time.time(),
            source="connect",
        )
        job = detail.get("job_info") or {}
        if job:
            telemetry.job = JobState(
                job_id=job.get("id"),
                state=raw_state,
                display_name=str(job.get("display_name") or ""),
                progress_percent=float(job.get("progress") or 0.0),
                time_remaining_seconds=int(job.get("time_remaining") or 0),
                time_printing_seconds=int(job.get("time_printing") or 0),
                total_height=float(job.get("total_height") or 0.0),
                layer_height=self._layer_height(job.get("id")),
            )
        telemetry.interpreted_phase = interpret_phase(telemetry)
        return telemetry

    def _layer_height(self, job_id: Any) -> float:
        # Only the job list carries the file's slicing metadata; fetched once per job.
        if not isinstance(job_id, int):
            return 0.0
        if job_id not in self._layer_heights:
            data = self._request(f"{CONNECT_BASE}/app/printers/{self.printer_uuid}/jobs?limit=3")
            meta = next(((j.get("file") or {}).get("meta") or {} for j in data.get("jobs") or [] if j.get("id") == job_id), {})
            self._layer_heights[job_id] = float(meta.get("layer_height") or 0.0)
        return self._layer_heights[job_id]
