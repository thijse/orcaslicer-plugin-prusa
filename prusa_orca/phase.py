"""Interprets raw telemetry into safe operational print phases."""

from __future__ import annotations

from .model import InterpretedPhase, PrinterTelemetry, RawPrinterState


def interpret_phase(telemetry: PrinterTelemetry) -> InterpretedPhase:
    """Classify printer state into a diagnostic phase.

    Distinguishes startup rituals, probing, cold wait, active printing,
    and different kinds of ATTENTION dialogs.
    """
    if not telemetry.connected:
        return InterpretedPhase.OFFLINE

    state = telemetry.raw_state
    progress = telemetry.job.progress_percent
    target_bed = telemetry.bed_target_temperature
    actual_bed = telemetry.bed_temperature
    target_nozzle = telemetry.nozzle_target_temperature
    actual_nozzle = telemetry.nozzle_temperature
    axis_z = telemetry.axis_z

    if state == RawPrinterState.ATTENTION:
        if progress > 0.0:
            return InterpretedPhase.ATTENTION_MID_PRINT
        if target_bed > 0.0 or target_nozzle > 0.0:
            return InterpretedPhase.ATTENTION_DURING_STARTUP
        return InterpretedPhase.ATTENTION_BEFORE_HEATING

    if state == RawPrinterState.PAUSED:
        return InterpretedPhase.PAUSED

    if state == RawPrinterState.FINISHED:
        return InterpretedPhase.FINISHED

    if state == RawPrinterState.STOPPED:
        return InterpretedPhase.STOPPED

    if state == RawPrinterState.ERROR:
        return InterpretedPhase.ERROR

    if state in (RawPrinterState.IDLE, RawPrinterState.READY):
        return InterpretedPhase.IDLE

    if state in (RawPrinterState.PRINTING, RawPrinterState.BUSY):
        if progress > 0.0:
            return InterpretedPhase.PRINTING

        # Progress is 0.0; inspect heaters and axis to determine startup step
        if target_bed > 0.0 and actual_bed < (target_bed - 3.0):
            return InterpretedPhase.HEATING_BED

        # Probe cooling: nozzle cooled below printing temp while bed is warm
        if target_nozzle > 0.0 and target_nozzle <= 170.0 and actual_nozzle > (target_nozzle + 5.0):
            return InterpretedPhase.COOLING_FOR_PROBE

        # Probing: negative Z or near zero during bed leveling
        if axis_z is not None and axis_z <= 0.5 and actual_bed >= (target_bed - 5.0):
            return InterpretedPhase.PROBING

        if target_nozzle > 170.0 and actual_nozzle < (target_nozzle - 2.0):
            return InterpretedPhase.REHEATING

        return InterpretedPhase.FIRST_LAYER

    return InterpretedPhase.IDLE
