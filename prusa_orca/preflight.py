"""Checks before a sliced plate is sent to the printer: problems block the print, warnings ask first."""

from __future__ import annotations

from dataclasses import dataclass, field

from .gcode_meta import GcodeMeta
from .model import PrinterTelemetry, RawPrinterState
from .printers import is_prusa, model_for, same_model

READY_STATES = (RawPrinterState.IDLE, RawPrinterState.READY, RawPrinterState.FINISHED, RawPrinterState.STOPPED)


@dataclass
class Preflight:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and not self.warnings


def _norm(text: str) -> str:
    return (text or "").strip().upper()


def check(meta: GcodeMeta, telemetry: PrinterTelemetry | None, print_after: bool) -> Preflight:
    result = Preflight()
    if telemetry is None or not telemetry.connected:
        result.warnings.append("The printer's status is unknown, so the tools couldn't be checked.")
        return result
    if print_after and telemetry.raw_state not in READY_STATES:
        result.problems.append(f"The printer is {telemetry.raw_state.value.lower()}; it can start a print only when idle.")
    model = model_for(telemetry.printer_type)
    printer_name = model.name if model else telemetry.model or "this printer"
    if meta.printer_model and not is_prusa(meta.printer_model):
        result.warnings.append(
            f"The plate was sliced for {meta.printer_model}, not a Prusa printer. "
            f"Its start G-code, speeds and limits may not suit the {printer_name}."
        )
    elif model and meta.printer_model and not same_model(meta.printer_model, model):
        result.warnings.append(f"The plate was sliced for {meta.printer_model}, but the printer is a {model.name}.")
    tools = {t.index: t for t in telemetry.tools}
    for i, wanted in enumerate(meta.filament_types):
        if not meta.used(i):
            continue
        tool = tools.get(i)
        label = tool.label if tool else f"T{i + 1}"
        if tool is None:
            result.problems.append(f"{label} is used by the plate but the printer has no tool {i + 1}.")
            continue
        if not tool.is_loaded or not tool.material:
            result.warnings.append(f"{label}: sliced for {wanted}, but the printer reports no filament.")
        elif _norm(tool.material) != _norm(wanted):
            result.warnings.append(f"{label}: sliced for {wanted}, but {tool.material} is loaded.")
        # An MMU's slots share the one nozzle, so Orca lists a single diameter.
        sliced = (
            meta.nozzle_diameters[i if tool.kind == "head" else 0]
            if len(meta.nozzle_diameters) > (i if tool.kind == "head" else 0)
            else 0
        )
        nozzle_owner = tool.kind == "head" or i == min(meta.used_tools or [0])
        if sliced and abs(sliced - tool.nozzle_diameter) > 1e-6 and nozzle_owner:
            result.warnings.append(
                f"{label}: sliced for a {sliced:g} mm nozzle, but the printer has {tool.nozzle_diameter:g} mm."
            )
        if nozzle_owner and meta.high_flow and not tool.high_flow:
            result.warnings.append(
                f"{label}: sliced for a high-flow nozzle, but the printer reports a standard one; "
                "it may not keep up with the flow."
            )
        elif nozzle_owner and tool.high_flow and not meta.high_flow and model and model.hf_presets:
            result.warnings.append(
                f"{label}: the printer has a high-flow nozzle, but the plate was sliced with a standard nozzle preset."
            )
        if meta.abrasive(i) and not tool.hardened:
            result.warnings.append(
                f"{label}: {wanted} is abrasive and wears a non-hardened nozzle; "
                "the printer reports no hardened nozzle on this tool."
            )
    return result


def check_reprint(meta: GcodeMeta, telemetry: PrinterTelemetry | None) -> Preflight:
    """Checks before printing a stored file again; the tools may have changed since it was sent."""
    if not meta.filament_types:
        return Preflight()
    return check(meta, telemetry, print_after=True)


def message(result: Preflight, file_name: str, action: str = "send") -> str:
    lines = [f"Before {'printing' if action == 'print' else 'sending'} {file_name}:"]
    lines += [f"- {p}" for p in result.problems + result.warnings]
    if not result.problems:
        lines.append(f"\n{action.capitalize()} it anyway?")
    return "\n".join(lines)
