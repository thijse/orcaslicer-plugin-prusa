"""Client for a running OrcaSlicer's MCP server, shared by the scripts in tools/.

Set ORCASLICER_SRC to the OrcaSlicer source folder (for tools/mcp/orca_mcp.py).
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.environ.get("ORCASLICER_SRC", r"D:\Github\OrcaSlicer"), "tools", "mcp"))
from orca_mcp import OrcaMcp


def connect() -> OrcaMcp:
    path = os.path.join(os.environ["APPDATA"], "OrcaSlicer", "mcp", "server.json")
    with open(path, encoding="utf-8") as f:
        info = json.load(f)
    return OrcaMcp(port=int(info["port"]), token=info["token"])
