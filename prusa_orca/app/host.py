"""The `orca` module (None outside OrcaSlicer), plugin identity, result codes and the logger."""

from __future__ import annotations

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

__version__ = "0.2.0"
AGENT_ID = "prusa3d_plugin"
AGENT_NAME = "Prusa (Link + Connect)"
PAGE_NAME = "Prusa"
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
