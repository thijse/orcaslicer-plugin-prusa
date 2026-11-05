"""Prusa Buddy printer models: Connect's printer type, Orca's printer model id, limits and art.

Type triples and codes are from Prusa-Firmware-Buddy include/common/printer_model_data.hpp.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class PrinterModel:
    code: str  # firmware id_str, e.g. "MK4S"
    name: str
    family: str  # art and defaults: mk4, mini, coreone, xl
    orca_model: str  # model_id in Orca's Prusa vendor profile
    orca_model_mmu: str = ""  # with an MMU3 attached
    nozzle_max: int = 290
    bed_max: int = 120
    chamber: bool = False
    orca_name: str = ""  # Orca's printer_model name when it differs from `name` (G-code check)
    hf_presets: bool = False  # Orca has high-flow nozzle presets for it, so a plain preset on an HF nozzle is a mismatch

    @property
    def sliced_name(self) -> str:
        return self.orca_name or self.name


# Connect printer_type ("type.version.subversion") -> model.
MODELS: dict[str, PrinterModel] = {
    "1.3.5": PrinterModel("MK3.5", "Prusa MK3.5", "mk4", "MK3.5"),
    "1.3.6": PrinterModel("MK3.5S", "Prusa MK3.5S", "mk4", "MK3.5", orca_name="Prusa MK3.5"),
    "1.3.9": PrinterModel("MK3.9", "Prusa MK3.9", "mk4", "MK4", orca_name="Prusa MK4"),
    "1.3.10": PrinterModel("MK3.9S", "Prusa MK3.9S", "mk4", "MK4S", orca_name="Prusa MK4S"),
    "1.4.0": PrinterModel("MK4", "Prusa MK4", "mk4", "MK4", "MK4ISMMU3"),
    "1.4.1": PrinterModel("MK4S", "Prusa MK4S", "mk4", "MK4S", "MK4ISMMU3", hf_presets=True),
    "2.1.0": PrinterModel("MINI", "Prusa MINI", "mini", "MINI", nozzle_max=280, bed_max=100),
    "3.1.0": PrinterModel("XL", "Prusa XL", "xl", "Prusa XL"),
    "3.1.1": PrinterModel("XLP", "Prusa XL+", "xl", "Prusa XL", orca_name="Prusa XL"),
    "7.1.0": PrinterModel("COREONE", "Prusa CORE One", "coreone", "Prusa_CORE_One", "Prusa_CORE_One_MMU3", chamber=True,
                           hf_presets=True),
    "7.10.0": PrinterModel("COREONEINDX", "Prusa CORE One INDX", "coreone", "prusa_coreone_indx_4t", chamber=True,
                            hf_presets=True),
    "8.1.0": PrinterModel("COREONEL", "Prusa CORE One L", "coreone", "Prusa_CORE_One_L", chamber=True, hf_presets=True),
    "8.10.0": PrinterModel("COREONEL-INDX", "Prusa CORE One L INDX", "coreone", "Prusa_CORE_One_L", chamber=True,
                           orca_name="Prusa CORE One L"),
}

# Orca has separate profiles for the XL by tool count and the INDX by head count.
_XL_BY_TOOLS = {5: "prusa_xl_5t_01"}
_INDX_BY_TOOLS = {8: "prusa_coreone_indx_8t"}


def model_for(printer_type: str) -> Optional[PrinterModel]:
    return MODELS.get((printer_type or "").strip())


def is_prusa(orca_printer_model: str) -> bool:
    return (orca_printer_model or "").strip().upper().startswith("PRUSA")


def same_model(orca_printer_model: str, model: PrinterModel) -> bool:
    """Orca's printer_model ("Prusa CORE One HF", "Prusa XL 5T", "Prusa MINIIS") names this printer model.

    Variants Orca keeps as separate models (MMU3, HF nozzle, input shaper, tool count) count as the same printer.
    """
    def base(text: str) -> str:
        text = re.sub(r"\b(MMU3|HF|IS|INDX|\d+T)\b", " ", text.upper().replace("MINIIS", "MINI"))
        return " ".join(text.replace("+", "").split())
    return base(orca_printer_model) == base(model.sliced_name)


def orca_model_id(model: PrinterModel, heads: int, mmu: bool) -> str:
    """Orca printer model for this printer as configured (MMU attached, number of heads)."""
    if mmu and model.orca_model_mmu:
        return model.orca_model_mmu
    if model.family == "xl":
        return _XL_BY_TOOLS.get(heads, model.orca_model)
    if model.code == "COREONEINDX":
        return _INDX_BY_TOOLS.get(heads, model.orca_model)
    return model.orca_model


def identify(detail: dict[str, Any], heads: int, mmu: bool) -> dict[str, str]:
    """Printer settings derived from a Connect printer record; empty when the type is unknown."""
    model = model_for(str(detail.get("printer_type") or ""))
    if model is None:
        return {}
    return {"model": model.code, "family": model.family, "model_id": orca_model_id(model, heads, mmu),
            "model_name": model.name}
