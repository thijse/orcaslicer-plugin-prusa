"""Run JavaScript in the Prusa tab's webview through Orca's MCP server and print the result.

Usage: python tools/page_eval.py "<script>"   (the webview is found in a fresh ui_snapshot)
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.environ.get("ORCASLICER_SRC", r"D:\Github\OrcaSlicer"), "tools", "mcp"))
from orca_mcp import OrcaMcp  # noqa: E402

info = json.load(open(os.path.join(os.environ["APPDATA"], "OrcaSlicer", "mcp", "server.json")))
o = OrcaMcp(port=int(info["port"]), token=info["token"])
snap = o.call_with_text("ui_snapshot")[1][0]
refs = re.findall(r'\[(w\d+)\] webview = "about:blank', snap)
if not refs:
    sys.exit("Prusa webview not found in ui_snapshot")
print(o.call("webview_eval", target=refs[0], script=sys.argv[1]))
