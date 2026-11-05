"""Canonical printer and multi-tool data model for Prusa integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RawPrinterState(StrEnum):
    IDLE = "IDLE"
    BUSY = "BUSY"
    PRINTING = "PRINTING"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"
    ATTENTION = "ATTENTION"
    READY = "READY"
    UNKNOWN = "UNKNOWN"


class InterpretedPhase(StrEnum):
    OFFLINE = "offline"
    IDLE = "idle"
    HEATING_BED = "heating_bed"
    COOLING_FOR_PROBE = "cooling_for_probe"
    PROBING = "probing"
    REHEATING = "reheating"
    FIRST_LAYER = "first_layer"
    PRINTING = "printing"
    PAUSED = "paused"
    ATTENTION_BEFORE_HEATING = "attention_before_heating"
    ATTENTION_DURING_STARTUP = "attention_during_startup"
    ATTENTION_MID_PRINT = "attention_mid_print"
    FINISHED = "finished"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ToolState:
    index: int  # 0-indexed tool (0 .. tools_count - 1)
    tool_number: int  # 1-indexed (T1 .. T5)
    name: str = ""  # e.g. "Prusament PLA" or generic material
    material: str = ""  # e.g. "PLA", "PETG", "FLEX"
    vendor: str = ""
    color: str = "#FFFFFF"  # "#RRGGBB"
    filament_id: str = ""  # OrcaSlicer preset filament_id if resolved
    nozzle_diameter: float = 0.4
    temperature: float = 0.0
    target_temperature: float = 0.0
    min_temp: int = 190
    max_temp: int = 250
    high_flow: bool = False
    hardened: bool = False
    is_active: bool = False
    is_loaded: bool = True
    # "head" for a toolhead (XL, INDX, single-tool), "slot" for an MMU3 feeder slot of head 0.
    kind: str = "head"
    connect_id: str = ""  # Connect tool id: "<head>" or "<head>.<slot>"

    @property
    def label(self) -> str:
        return f"T{self.tool_number}" if self.kind == "head" else f"Slot {self.tool_number}"


@dataclass
class JobState:
    job_id: int | None = None
    state: RawPrinterState = RawPrinterState.IDLE
    file_name: str = ""
    display_name: str = ""
    progress_percent: float = 0.0
    time_remaining_seconds: int = 0
    time_printing_seconds: int = 0
    layer_num: int = 0
    total_layer_num: int = 0
    total_height: float = 0.0
    layer_height: float = 0.0

    def estimate_layers(self, z: float | None, previous: int = 0) -> None:
        """Layer numbers from heights; the printer reports none. `previous` is the last estimate for this job."""
        if self.layer_height <= 0 or self.total_height <= 0:
            return
        self.total_layer_num = round(self.total_height / self.layer_height)
        self.layer_num = previous
        if z is None:
            return
        layer = min(self.total_layer_num, round(float(z) / self.layer_height))
        # The XL probes and parks high before the first layer, and lifts the head on pause or
        # tool change, so start counting at the first layer and only accept small steps upward.
        if previous == 0 and layer > 1:
            # Joining a print already under way (e.g. after a restart): Z is the layer once printing has progressed.
            if self.progress_percent >= 10 and z <= self.total_height:
                self.layer_num = layer
            return
        if previous <= layer <= previous + 5:
            self.layer_num = max(layer, 1)


@dataclass
class DialogInfo:
    dialog_id: str = ""
    title: str = ""
    message: str = ""
    options: list[str] = field(default_factory=list)
    active: bool = False


@dataclass
class PrinterTelemetry:
    connected: bool = False
    raw_state: RawPrinterState = RawPrinterState.UNKNOWN
    interpreted_phase: InterpretedPhase = InterpretedPhase.OFFLINE
    model: str = "Original Prusa XL"
    printer_type: str = ""  # Connect's "type.version.subversion", e.g. "3.1.0"
    mmu_enabled: bool = False
    hostname: str = ""
    firmware_version: str = ""
    uuid: str = ""
    serial_number: str = ""
    ip_address: str = ""

    # Temperatures
    nozzle_temperature: float = 0.0
    nozzle_target_temperature: float = 0.0
    bed_temperature: float = 0.0
    bed_target_temperature: float = 0.0

    # Motion & flow
    flow_percent: int = 100
    speed_percent: int = 100
    fan_speed_pwm: int = 0
    fan_print_rpm: int = 0
    fan_hotend_rpm: int = 0
    axis_x: float | None = None
    axis_y: float | None = None
    axis_z: float | None = None

    # Multi-tool
    tools: list[ToolState] = field(default_factory=list)
    active_tool: int = 0

    # Job & storage
    job: JobState = field(default_factory=JobState)
    storage_available: bool = True
    active_dialog: DialogInfo | None = None

    # Telemetry metadata
    last_updated: float = 0.0
    source: str = "none"  # "lan", "connect", "mock"

    @property
    def is_printing(self) -> bool:
        return self.raw_state in (RawPrinterState.PRINTING, RawPrinterState.BUSY)
