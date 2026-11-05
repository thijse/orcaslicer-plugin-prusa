"""Orca notifications for print events and failed actions."""

from __future__ import annotations

from typing import Any

from .host import LOG, orca


EVENT_TEXT = {
    "started": ("PrintInfoShortNotificationLevel", "Printing {file} on {printer}."),
    "first_layer": ("PrintInfoShortNotificationLevel", "{file}: first layer done; check it in the Prusa tab."),
    "near_end": ("PrintInfoShortNotificationLevel", "{file} finishes in about 10 minutes."),
    "paused": ("WarningNotificationLevel", "{file} is paused."),
    "attention": ("SeriousWarningNotificationLevel", "{printer} needs attention: {error}"),
    "finished": ("PrintInfoNotificationLevel", "{file} finished on {printer}."),
    "stopped": ("WarningNotificationLevel", "{file} was stopped at {progress:.0f}%."),
    "failed": ("ErrorNotificationLevel", "{file} failed: {error}"),
}


COMMAND_LABELS = {
    "SET_NOZZLE_TEMPERATURE": "Setting nozzle temperature", "SET_HEATBED_TEMPERATURE": "Setting bed temperature",
    "SET_SPEED": "Setting print speed", "SET_FLOW": "Setting flow", "MOVE": "Moving", "MOVE_Z": "Moving Z",
    "MOVE_E": "Moving filament", "HOME": "Homing", "DISABLE_STEPPERS": "Turning motors off",
    "SET_TOOL_NOZZLE_DIAMETER": "Changing tool settings", "SET_TOOL_HARDENED": "Changing tool settings",
}


def command_label(name: str) -> str:
    return COMMAND_LABELS.get(name, name.replace("_", " ").capitalize())


def warn(text: str) -> None:
    """An Orca warning notification for a failed action the user started outside the Prusa tab."""
    LOG.warning("%s", text)
    if orca is None:
        return
    try:
        orca.host.ui.push_notification(orca.host.ui.NotificationLevel.WarningNotificationLevel, f"Prusa: {text}")
    except Exception:
        LOG.exception("notification failed")


def notify(event: str, record: dict[str, Any]) -> None:
    """An Orca notification for a print event, unless turned off in the plugin settings."""
    if orca is None or event not in EVENT_TEXT:
        return
    from .runtime import runtime

    events = runtime().settings.values.get("notify", {})
    if not events.get(event, True):
        return
    level, template = EVENT_TEXT[event]
    printer = runtime().settings.values["printer"].get("name") or "the printer"
    text = template.format(file=record.get("file", ""), printer=printer, error=record.get("error") or "see the printer",
                           progress=float(record.get("progress") or 0))
    try:
        orca.host.ui.push_notification(getattr(orca.host.ui.NotificationLevel, level), text)
    except Exception:
        LOG.exception("notification failed")


