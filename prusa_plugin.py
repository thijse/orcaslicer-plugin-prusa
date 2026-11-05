# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# name = "Prusa Integration"
# description = "Printer agent and Prusa tab for Buddy-firmware Prusa printers (PrusaLink + Prusa Connect)."
# author = "Thijs"
# version = "0.2.0"
# ///
"""OrcaSlicer plugin entry: Prusa printer agent (Device tab, filament sync) and a Prusa tab."""

from __future__ import annotations

import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from prusa_orca.app.host import orca

if orca is not None:
    from prusa_orca.app.agent import PrusaPrinterAgent
    from prusa_orca.app.orca_state import _configured_hosts
    from prusa_orca.app.page import PrusaPage

    @orca.plugin
    class PrusaPlugin(orca.base):
        def register_capabilities(self) -> None:
            hosts = [
                "https://account.prusa3d.com",
                "https://connect.prusa3d.com",
                "https://connect-api.prusa3d.com",
                "https://camera-service-snapshots.prusa3d.com",
                # The local server that hands Connect camera snapshots to Orca's Device tab binds here.
                "http://127.0.0.1",
            ]
            hosts += _configured_hosts()
            # network= grants whole hosts up front; network_http only covers exact URLs and
            # would prompt again for every PrusaLink endpoint the poller calls.
            # Print jobs arrive as a .gcode.3mf in Orca's temp model folder, outside the plugin's allowed roots.
            jobs = os.path.join(tempfile.gettempdir(), "orcaslicer_model", "*")
            orca.request_permissions(network=hosts, fs_read=[jobs], threading=True)
            orca.register_capability(PrusaPrinterAgent)
            orca.register_capability(PrusaPage)
