"""The `orca` module (None outside OrcaSlicer), plugin identity, result codes and the logger."""

from __future__ import annotations

import contextlib
import importlib
import logging
import os
import sys
from typing import Any


def _load_orca() -> Any:
    """OrcaSlicer's embedded `orca` module, or None outside OrcaSlicer. It has no type stubs, hence Any."""
    try:
        module = importlib.import_module("orca")
    except ImportError:
        return None
    return module if hasattr(module, "printer_agent") and hasattr(module, "register_capability") else None


orca: Any = _load_orca()

__version__ = "0.3.0b1"
AGENT_ID = "prusa3d_plugin"
AGENT_NAME = "Prusa (Link + Connect)"
PAGE_NAME = "Prusa"
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def install_info() -> dict[str, str]:
    """Version and how this copy is installed: a .whl Orca extracted, or a plain folder (possibly a link to a checkout)."""
    packaged = "__whl_extracted__" in PLUGIN_DIR.replace("\\", "/").split("/")
    location = PLUGIN_DIR
    with contextlib.suppress(OSError):
        target = os.path.realpath(PLUGIN_DIR)
        if os.path.normcase(target) != os.path.normcase(PLUGIN_DIR):
            location = f"{PLUGIN_DIR} -> {target}"
    return {"version": __version__, "kind": "package (.whl)" if packaged else "folder", "location": location}


OK = 0
ERR_NOT_SUPPORTED = -7010
ERR_BUSY = -1
# SendingPrintJobStage (slic3r/Utils/bambu_networking.hpp)
STAGE_CREATE, STAGE_UPLOAD, STAGE_FINISHED, STAGE_ERROR = 0, 1, 6, 7

LOG = logging.getLogger("prusa_orca")
if not LOG.handlers:
    _stderr = logging.StreamHandler(sys.stderr)
    _stderr.setFormatter(logging.Formatter("%(asctime)s prusa_orca %(levelname)s %(message)s"))
    LOG.addHandler(_stderr)
LOG.setLevel(logging.INFO)
