"""Dev helper: print open dialogs and the UI snapshot section starting at an optional marker.

Usage: python tools/orca_ui.py [marker] [length]
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.environ.get("ORCASLICER_SRC", r"D:\Github\OrcaSlicer"), "tools", "mcp"))
from orca_mcp import OrcaMcp  # noqa: E402

info = json.load(open(os.path.join(os.environ["APPDATA"], "OrcaSlicer", "mcp", "server.json")))
o = OrcaMcp(port=int(info["port"]), token=info["token"])
for d in o.call("get_state")["dialogs"]:
    print("DIALOG:", d["title"], "|", d.get("message", "")[:600].replace("\n", " / "),
          "| buttons:", [b["label"] for b in d.get("buttons", [])][:12])
marker = sys.argv[1] if len(sys.argv) > 1 else ""
length = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
snap = o.call_with_text("ui_snapshot")[1][0]
k = snap.find(marker) if marker else 0
if k > 0:
    k = snap.rfind("\n", 0, k) + 1
print(snap[max(k, 0):max(k, 0) + length])
