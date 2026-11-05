"""Converts Prusa canonical telemetry into Bambu-dialect JSON for OrcaSlicer."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, cast

from .model import PrinterTelemetry, RawPrinterState, ToolState


def normalize_hex(color: str | None, default: str = "#FFFFFF") -> str:
    """Normalize color to #RRGGBB format."""
    if not color:
        return default
    c = color.strip()
    if c.startswith("#"):
        c = c[1:]
    if c.startswith("0x"):
        c = c[2:]
    c = "".join(ch for ch in c if ch in "0123456789abcdefABCDEF")
    if len(c) == 8:
        c = c[:6]
    if len(c) != 6:
        return default
    return "#" + c.upper()


def hex_to_bbl(color: str) -> str:
    """Convert #RRGGBB to Bambu's expected RRGGBBFF format."""
    c = normalize_hex(color)[1:]
    return c + "FF"


def map_gcode_state(raw_state: RawPrinterState) -> str:
    """Map RawPrinterState to Bambu gcode_state string."""
    if raw_state in (RawPrinterState.PRINTING, RawPrinterState.BUSY):
        return "RUNNING"
    if raw_state == RawPrinterState.PAUSED:
        return "PAUSE"
    if raw_state == RawPrinterState.FINISHED:
        return "FINISH"
    if raw_state == RawPrinterState.ATTENTION:
        return "PAUSE"
    return "IDLE"


def build_ams_units(tools: list[ToolState], filament_id_for: Callable[[ToolState], str] | None = None) -> dict[str, Any]:
    """Tools as 4-tray AMS units: tools 1-4 in unit 0, tool 5 in unit 1."""
    ams_units: list[dict[str, Any]] = []
    ams_exist_bits = 0
    tray_exist_bits = 0

    unit_count = (len(tools) + 3) // 4 if tools else 1
    for u_idx in range(unit_count):
        ams_exist_bits |= 1 << u_idx
        trays: list[dict[str, Any]] = []
        # Only real tools get a slot: padding slots would sync as extra filaments (5 tools, not 8).
        for s_idx in range(min(4, max(1, len(tools) - u_idx * 4))):
            tool_idx = u_idx * 4 + s_idx
            tray: dict[str, Any] = {
                "id": str(s_idx),
                "tag_uid": "0000000000000000",
            }
            if tool_idx < len(tools) and tools[tool_idx].is_loaded and tools[tool_idx].material:
                t = tools[tool_idx]
                tray_exist_bits |= 1 << tool_idx
                tray["tray_info_idx"] = (filament_id_for(t) if filament_id_for else "") or t.filament_id or f"PRUSA-{t.material}"
                tray["tray_type"] = t.material
                tray["tray_sub_brands"] = " ".join(x for x in (t.vendor, t.name) if x) or t.material
                # No colour on the printer (no NFC, no name assigned): grey reads as "unknown".
                tray["tray_color"] = hex_to_bbl(t.color or "#9E9E9E")
                tray["tray_diameter"] = "1.75"
                tray["remain"] = 100
                tray["nozzle_temp_min"] = str(t.min_temp)
                tray["nozzle_temp_max"] = str(t.max_temp)
                tray["cols"] = [tray["tray_color"]]
                tray["ctype"] = 0
            else:
                tray["tray_info_idx"] = ""
                tray["tray_type"] = ""
                tray["tray_color"] = "00000000"
                tray["tray_slot_placeholder"] = "1"
            trays.append(tray)

        ams_units.append(
            {
                "id": str(u_idx),
                "info": "0002",
                "tray": trays,
            }
        )

    return {
        "ams": ams_units,
        "ams_exist_bits": format(ams_exist_bits, "X"),
        "tray_exist_bits": format(tray_exist_bits, "X"),
        "tray_is_bbl_bits": "0",
        "tray_read_done_bits": format(tray_exist_bits, "X"),
        "tray_reading_bits": "0",
        "version": 1,
        "insert_flag": True,
        "power_on_flag": False,
    }


def _active_tool(telemetry: PrinterTelemetry) -> ToolState:
    for tool in telemetry.tools:
        if tool.is_active:
            return tool
    return telemetry.tools[0]


from .printers import model_for  # noqa: E402


def limits(telemetry: PrinterTelemetry) -> tuple[int, int]:
    """(nozzle max, bed max) for the connected model; XL values when unknown."""
    model = model_for(telemetry.printer_type)
    return (model.nozzle_max, model.bed_max) if model else (290, 120)


def build_push_status(
    telemetry: PrinterTelemetry, sequence_id: int, filament_id_for: Callable[[ToolState], str] | None = None
) -> dict[str, Any]:
    """Build complete push_status payload expected by OrcaSlicer DeviceManager."""
    state_str = map_gcode_state(telemetry.raw_state)
    stage = "2" if telemetry.is_printing else "1"

    p: dict[str, Any] = {
        "command": "push_status",
        "msg": 0,
        "sequence_id": str(sequence_id),
        "support_mqtt_alive": True,
        "gcode_state": state_str,
        "mc_print_stage": stage,
        "mc_print_error_code": "0",
        "print_error": 0,
        # Bits 0-2: X/Y/Z homed. The XL doesn't report it and homes before moving, so Orca's jog pad
        # shouldn't stop at its recenter dialog. Bits 8-9 are the storage state (1 = present).
        "home_flag": 0b111 | ((1 << 8) if telemetry.storage_available else 0),
        "nozzle_temp_range": [0, limits(telemetry)[0]],
        "bed_temp_range": [0, limits(telemetry)[1]],
        "sdcard": telemetry.storage_available,
        "support_bed_leveling": 1,
        "support_send_to_sd": True,
        "nozzle_temper": telemetry.nozzle_temperature,
        "nozzle_target_temper": telemetry.nozzle_target_temperature,
        "bed_temper": telemetry.bed_temperature,
        "bed_target_temper": telemetry.bed_target_temperature,
        # Single-extruder fields Orca uses to pick the printer preset and accept AMS sync.
        "nozzle_diameter": f"{_active_tool(telemetry).nozzle_diameter:.1f}" if telemetry.tools else "0.4",
        "nozzle_type": "hardened_steel" if telemetry.tools and _active_tool(telemetry).hardened else "stainless_steel",
        "mc_percent": int(telemetry.job.progress_percent),
        "mc_remaining_time": max(0, telemetry.job.time_remaining_seconds // 60),
        "ams": build_ams_units(telemetry.tools, filament_id_for),
    }

    if telemetry.job.file_name or telemetry.job.display_name:
        p["gcode_file"] = telemetry.job.file_name
        p["subtask_name"] = telemetry.job.display_name or telemetry.job.file_name
    if telemetry.job.total_layer_num:
        p["layer_num"] = telemetry.job.layer_num
        p["total_layer_num"] = telemetry.job.total_layer_num

    return {"print": p}


def build_get_version(telemetry: PrinterTelemetry, sequence_id: int) -> dict[str, Any]:
    """Provide module info so is_info_ready() succeeds in C++."""
    return {
        "info": {
            "command": "get_version",
            "sequence_id": str(sequence_id),
            "module": [
                {
                    "name": "ota",
                    "project_name": telemetry.model,
                    "product_name": telemetry.model or "Original Prusa",
                    "sw_ver": telemetry.firmware_version or "8.0.1",
                    "hw_ver": telemetry.model,
                    "sn": telemetry.serial_number or telemetry.uuid,
                }
            ],
        }
    }


def tool_mapping_problem(ams_mapping: str) -> str:
    """Why Orca's filament-to-tray mapping can't be printed from a file as is, or "" when it can.

    A file printed through PrusaLink uses the tools its G-code names, so filament N must sit in tool N.
    """
    try:
        slots: object = json.loads(ams_mapping) if ams_mapping.strip().startswith("[") else []
    except ValueError:
        return ""
    for index, item in enumerate(cast(list[object], slots)):
        if not isinstance(item, (int, float, str)):
            continue
        try:
            slot = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= slot < 254 and slot != index:
            return (
                f"Filament {index + 1} is mapped to tool {slot + 1}. The XL prints a file with the tools it was "
                f"sliced for, so put each filament on its own tool number and slice again."
            )
    return ""


def map_ams_to_prusa_tool_mapping(ams_mapping: str, tools_count: int = 5) -> dict[str, list[int]]:
    """Convert OrcaSlicer ams_mapping string into Prusa START_PRINT tool_mapping.

    Orca passes mapping like '0:0,1:1,2:2' (slicer_extruder:ams_slot).
    Prusa Connect START_PRINT expects 1-based indices: {'1': [1], '2': [2]}.
    """
    mapping: dict[str, list[int]] = {}
    if not ams_mapping:
        return {str(i + 1): [i + 1] for i in range(tools_count)}

    try:
        # ams_mapping format can be "0:0,1:1" or a JSON list
        if ams_mapping.startswith("["):
            import json

            parsed = json.loads(ams_mapping)
            for idx, slot in enumerate(parsed):
                slicer_idx = idx + 1
                tool_target = int(slot) + 1
                mapping[str(slicer_idx)] = [tool_target]
        else:
            pairs = ams_mapping.split(",")
            for pair in pairs:
                if ":" in pair:
                    s_idx, t_idx = pair.split(":", 1)
                    slicer_idx = int(s_idx) + 1
                    tool_target = int(t_idx) + 1
                    mapping[str(slicer_idx)] = [tool_target]
    except Exception:
        # Fallback to 1-to-1 mapping
        return {str(i + 1): [i + 1] for i in range(tools_count)}

    return mapping or {str(i + 1): [i + 1] for i in range(tools_count)}
