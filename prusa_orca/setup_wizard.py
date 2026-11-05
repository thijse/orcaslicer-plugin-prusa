"""Setup from Prusa Connect: everything the plugin needs, read from the printer and camera records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .jsonview import obj
from .printers import model_for


@dataclass
class Proposal:
    """Settings to apply, and what the user still has to do by hand."""

    patch: dict[str, Any] = field(default_factory=dict)
    found: list[str] = field(default_factory=list)  # "PrusaLink address: 192.168.1.50"
    missing: list[str] = field(default_factory=list)  # instructions for values Connect doesn't have
    notes: list[str] = field(default_factory=list)  # optional follow-ups


def _rtsp_camera(cameras: list[dict[str, Any]]) -> str | None:
    """IP of a camera that can stream RTSP (the Buddy3D), from Connect's camera list."""
    for cam in cameras:
        net = obj(cam, "config", "network_info")
        ip = net.get("wifi_ipv4") or net.get("lan_ipv4") or ""
        if ip and "RtspStream" in (cam.get("features") or []):
            return ip
    return None


def propose(detail: dict[str, Any], cameras: list[dict[str, Any]]) -> Proposal:
    """Settings from Connect's printer record (/app/printers/<uuid>) and its cameras (/app/printers/<uuid>/cameras)."""
    p = Proposal()
    model = model_for(str(detail.get("printer_type") or ""))
    name = str(detail.get("name") or "")
    p.patch = {"connect": {"printer_uuid": str(detail.get("uuid") or "")}, "prusalink": {}, "camera": {}, "printer": {}}
    if name:
        p.patch["printer"]["name"] = name
    label = name or (model.name if model else "unnamed")
    if model and model.name.lower() not in label.lower():
        label += f" ({model.name})"
    p.found.append(f"Printer: {label}")

    net = obj(detail, "network_info")
    ip = net.get("lan_ipv4") or net.get("wifi_ipv4") or ""
    if ip:
        p.patch["prusalink"]["host"] = ip
        p.found.append(f"PrusaLink address: {ip}")
    else:
        p.missing.append("PrusaLink address: on the printer, open Settings > Network and note the IP address.")

    key = detail.get("prusalink_api_key") or ""
    if key:
        # A stored password wins over the key (Settings.lan_secret), so drop it.
        p.patch["prusalink"].update({"api_key": key, "password": ""})
        p.found.append("PrusaLink API key")
    else:
        p.missing.append(
            "PrusaLink password: on the printer, open Settings > Network > PrusaLink. "
            "The user is 'maker'; the password is shown there."
        )

    cam = _rtsp_camera(cameras)
    if cam:
        p.patch["camera"]["rtsp_url"] = f"rtsp://{cam}/live"
        p.found.append(f"Camera stream: rtsp://{cam}/live")
        p.notes.append(
            "For a live camera in the Device tab, turn on RTSP in the camera's settings in Prusa Connect; "
            "until then the plugin shows Connect snapshots."
        )
    elif cameras:
        p.found.append("Camera: snapshots through Prusa Connect")
    return p
