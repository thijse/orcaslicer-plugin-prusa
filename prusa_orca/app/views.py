"""JSON views the Prusa tab renders."""

from __future__ import annotations

from typing import Any

from ..control import is_allowed, ready_action
from ..materials import FilamentPreset, match_preset
from ..model import ToolState
from .runtime import Runtime


def tool_view(tool: ToolState, presets: list[FilamentPreset]) -> dict[str, Any]:
    preset = match_preset(tool, presets)
    return {
        "tool_number": tool.tool_number,
        "label": tool.label,
        "material": tool.material,
        "name": tool.name,
        "vendor": tool.vendor,
        "color": tool.color,
        "is_loaded": tool.is_loaded,
        "is_active": tool.is_active,
        "nozzle_diameter": tool.nozzle_diameter,
        "hardened": tool.hardened,
        "high_flow": tool.high_flow,
        "temperature": tool.temperature,
        "target": tool.target_temperature,
        "preset": preset.name if preset else "",
    }


# Commands the Prusa tab's Control box can send.
CONTROL_COMMANDS = (
    "SET_NOZZLE_TEMPERATURE",
    "SET_HEATBED_TEMPERATURE",
    "SET_SPEED",
    "SET_FLOW",
    "MOVE",
    "MOVE_Z",
    "HOME",
    "DISABLE_STEPPERS",
)
# Extra settings the printer may offer (CORE One chamber, XL enclosure, flow), shown when supported-commands lists them.
EXTRA_COMMANDS = {
    "SET_CHAMBER_TEMPERATURE": "Chamber temperature (°C)",
    "SET_CHAMBER_FAN": "Chamber fan (%)",
    "SET_ENCLOSURE_ENABLED": "Enclosure",
    "SET_ENCLOSURE_PRINTING_FILTRATION": "Filtration while printing",
    "SET_ENCLOSURE_POSTPRINT": "Filtration after printing",
    "SET_ENCLOSURE_POSTPRINT_FILTRATION_TIME": "Post-print filtration (min)",
}


def extra_controls(rt: Runtime, state: str) -> list[dict[str, Any]]:
    """Single-argument commands from EXTRA_COMMANDS that this printer supports, with their argument."""
    backend = rt.backend
    cloud = backend.cloud if backend else None
    supported = rt.supported_commands()
    out = []
    for name, label in EXTRA_COMMANDS.items():
        args = (cloud.command_args if cloud else {}).get(name) or []
        if name not in supported or len(args) != 1:
            continue
        if name.startswith("SET_ENCLOSURE") and not ((cloud.printer_detail if cloud else {}).get("enclosure") or {}).get(
            "present"
        ):
            continue
        out.append(
            {
                "name": name,
                "label": label,
                "arg": args[0].get("name"),
                "type": args[0].get("type", "integer"),
                "enabled": is_allowed(supported, name, state),
            }
        )
    return out


def telemetry_view(rt: Runtime) -> dict[str, Any]:
    t = rt.snapshot
    backend = rt.backend
    base = {
        "logged_in": rt.tokens.logged_in,
        "error": backend.last_error if backend else "",
        "name": rt.settings.values["prusalink"].get("host", ""),
        "printer_name": rt.settings.values["printer"].get("name", ""),
        "family": rt.settings.values["printer"].get("family", "xl"),
        "model_name": rt.settings.values["printer"].get("model_name", ""),
    }
    if t is None:
        return {**base, "connected": False, "tools": [], "allowed": {}}
    supported = {} if rt.identity_error else rt.supported_commands()
    allowed = {name: True for name in CONTROL_COMMANDS if is_allowed(supported, name, t.raw_state.value)}
    if rt.identity_error:
        note = "Controls are off: PrusaLink and Prusa Connect point at different printers."
    elif not supported:
        note = "Log in to Prusa Connect to control temperatures and motion."
    elif not allowed:
        note = "The printer accepts no controls in its current state."
    else:
        note = "Moves while printing are blocked by the printer." if t.is_printing else ""
    base = {**base, "allowed": allowed, "control_note": note, "extras": extra_controls(rt, t.raw_state.value)}
    base["ready"] = ready_action(supported, t.raw_state.value) if t.connected else None
    base["tasks"] = [task.view() for task in rt.tasks.running() if not task.quiet]
    base["cloud_error"] = backend.last_error if backend else ""
    base["identity_error"] = rt.identity_error
    return {
        **base,
        "connected": t.connected,
        "phase": t.interpreted_phase.value,
        "model": t.model,
        "firmware": t.firmware_version,
        "ip": t.ip_address,
        "source": t.source,
        "nozzle_temp": t.nozzle_temperature,
        "nozzle_target": t.nozzle_target_temperature,
        "bed_temp": t.bed_temperature,
        "bed_target": t.bed_target_temperature,
        "progress": round(t.job.progress_percent, 1),
        "z": t.axis_z,
        "speed": t.speed_percent,
        "flow": t.flow_percent,
        "fan_print": t.fan_print_rpm,
        "fan_hotend": t.fan_hotend_rpm,
        "state": t.raw_state.value,
        "job": {
            "name": t.job.display_name or t.job.file_name,
            "file": t.job.file_name,
            "layer": t.job.layer_num,
            "layers": t.job.total_layer_num,
            "left": t.job.time_remaining_seconds,
            "printing": t.job.time_printing_seconds,
        }
        if t.job.job_id is not None
        else None,
        "tools": [
            {**tool_view(tool, rt.presets), "swap": s.to_json() if (s := rt.swaps.get(tool.tool_number)) else None}
            for tool in t.tools
        ],
    }
