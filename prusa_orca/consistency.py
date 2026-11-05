"""Checks that the printer, Prusa Connect and Orca's selected preset describe the same machine."""

from __future__ import annotations

from .printers import PrinterModel, is_prusa, same_model


def _norm_serial(serial: str) -> str:
    return "".join((serial or "").split()).upper()


def serial_mismatch(lan_serial: str, cloud_serial: str) -> str:
    """Error text when PrusaLink and the chosen Connect printer are different machines; "" when they match or one is unknown."""
    lan, cloud = _norm_serial(lan_serial), _norm_serial(cloud_serial)
    if not lan or not cloud or lan == cloud:
        return ""
    return (f"PrusaLink and Prusa Connect are set to different printers (serial {lan_serial} on the network, "
            f"{cloud_serial} in Connect). Controls are off until the host or the Connect printer in Settings is fixed.")


def preset_mismatch(orca_printer_model: str, preset_name: str, model: PrinterModel | None) -> str:
    """Notice when Orca's selected printer preset is not for the connected printer; "" when it is or is unknown."""
    if model is None or not orca_printer_model:
        return ""
    if not is_prusa(orca_printer_model):
        return (f"Orca's printer preset \"{preset_name}\" is not a Prusa printer, but the connected printer is a "
                f"{model.name}. Select a {model.name} preset before slicing for it.")
    if not same_model(orca_printer_model, model):
        return (f"Orca's printer preset \"{preset_name}\" is for the {orca_printer_model}, but the connected printer "
                f"is a {model.name}.")
    return ""
