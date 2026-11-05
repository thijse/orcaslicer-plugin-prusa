"""Combines LAN (fast, live) and Connect (per-tool materials) into one telemetry snapshot."""

from __future__ import annotations

import logging
import threading
import time

from ..consistency import serial_mismatch
from ..model import PrinterTelemetry, ToolState
from ..phase import interpret_phase
from ..tasks import reason as _reason
from .connect import ConnectBackend
from .prusalink import PrusaLinkBackend

LOG = logging.getLogger("prusa_orca.backends.aggregate")


def merge(
    lan: PrinterTelemetry | None, cloud: PrinterTelemetry | None, previous: PrinterTelemetry | None = None
) -> PrinterTelemetry | None:
    if lan is None:
        return cloud
    if cloud is None:
        return lan
    # LAN wins for live values; Connect supplies identity and the per-tool list.
    lan.tools = cloud.tools
    lan.active_tool = cloud.active_tool
    lan.model = cloud.model or lan.model
    lan.printer_type = cloud.printer_type or lan.printer_type
    lan.mmu_enabled = cloud.mmu_enabled
    lan.firmware_version = cloud.firmware_version or lan.firmware_version
    lan.uuid = cloud.uuid
    lan.serial_number = cloud.serial_number
    lan.hostname = cloud.hostname or lan.hostname
    # With no tool picked the XL's LAN API reports 0 for the nozzle; show the first tool instead.
    if not lan.nozzle_temperature and lan.tools:
        tool = next((t for t in lan.tools if t.is_active), lan.tools[0])
        lan.nozzle_temperature = tool.temperature
        lan.nozzle_target_temperature = tool.target_temperature
    if cloud.job.job_id is not None and lan.job.job_id is not None:
        lan.job.total_height = cloud.job.total_height
        lan.job.layer_height = cloud.job.layer_height
        lan.job.display_name = lan.job.display_name or cloud.job.display_name
        last = previous.job.layer_num if previous and previous.job.job_id == lan.job.job_id else 0
        lan.job.estimate_layers(lan.axis_z, last)
    lan.source = "lan+connect"
    lan.interpreted_phase = interpret_phase(lan)
    return lan


class AggregateBackend:
    def __init__(self, lan: PrusaLinkBackend | None, cloud: ConnectBackend | None, tools_interval: float = 30.0) -> None:
        self.lan = lan
        self.cloud = cloud
        self.tools_interval = tools_interval
        self._cloud_snapshot: PrinterTelemetry | None = None
        self._cloud_fetched_at = 0.0
        self._cloud_busy = False
        self.last_snapshot: PrinterTelemetry | None = None
        self.last_error = ""
        self.lan_serial: str | None = None  # read once from /api/v1/info

    @property
    def identity_error(self) -> str:
        """Set when the PrusaLink host and the Connect printer are different machines."""
        cloud = self._cloud_snapshot
        return serial_mismatch(self.lan_serial or "", cloud.serial_number if cloud else "")

    def refresh_tools(self) -> None:
        self._cloud_fetched_at = 0.0

    def _fetch_cloud(self) -> None:
        try:
            cloud = self.cloud.fetch_telemetry()
            # Connect now and then answers without the tool list; keep the last one rather than flash empty slots.
            if not cloud.tools and self._cloud_snapshot is not None:
                cloud.tools = self._cloud_snapshot.tools
                cloud.active_tool = self._cloud_snapshot.active_tool
                cloud.mmu_enabled = self._cloud_snapshot.mmu_enabled
            self._cloud_snapshot = cloud
            self.last_error = ""
        except Exception as exc:  # network, auth or schema change: keep LAN status going
            self.last_error = f"Connect: {_reason(exc)}"
            LOG.warning("Connect fetch failed: %s", exc)
        finally:
            self._cloud_fetched_at = time.time()
            self._cloud_busy = False

    def fetch_status(self) -> PrinterTelemetry | None:
        lan = None
        if self.lan is not None:
            lan = self.lan.fetch_status()
            if lan is not None and self.lan_serial is None:
                info = self.lan.fetch_info() or {}
                self.lan_serial = str(info.get("serial") or "")
        due = time.time() - self._cloud_fetched_at >= (self.tools_interval if lan is not None else 5.0)
        if self.cloud is not None and due and not self._cloud_busy:
            if lan is None:
                # Connect is the only source: wait for it (bounded by its request timeout).
                self._cloud_busy = True
                self._fetch_cloud()
            else:
                # A slow Connect must not hold up the LAN status; its answer joins a later poll.
                self._cloud_busy = True
                threading.Thread(target=self._fetch_cloud, name="prusa-connect-poll", daemon=True).start()
        # Tools and identity of another printer must not be shown or acted on as this one's.
        cloud = None if self.identity_error else self._cloud_snapshot
        snapshot = merge(lan, cloud, self.last_snapshot)
        if snapshot is not None and lan is not None and self.lan_serial:
            snapshot.serial_number = self.lan_serial
        if snapshot is not None:
            self.last_snapshot = snapshot
        return snapshot

    def tools(self) -> list[ToolState]:
        return self.last_snapshot.tools if self.last_snapshot else []
