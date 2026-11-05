"""The `orca` module (None outside OrcaSlicer), plugin identity, result codes and the logger."""

from __future__ import annotations

import logging
import os
import sys

try:
    import orca  # type: ignore

    if not (hasattr(orca, "printer_agent") and hasattr(orca, "register_capability")):
        orca = None
except ImportError:
    orca = None

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
