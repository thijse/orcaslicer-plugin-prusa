"""Dev helper: print open dialogs and the UI snapshot section starting at an optional marker.

Usage: python tools/orca_ui.py [marker] [length]
"""

import sys

from orca_client import connect

o = connect()
for d in o.call("get_state")["dialogs"]:
    print(
        "DIALOG:",
        d["title"],
        "|",
        d.get("message", "")[:600].replace("\n", " / "),
        "| buttons:",
        [b["label"] for b in d.get("buttons", [])][:12],
    )
marker = sys.argv[1] if len(sys.argv) > 1 else ""
length = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
snap = o.call_with_text("ui_snapshot")[1][0]
k = snap.find(marker) if marker else 0
if k > 0:
    k = snap.rfind("\n", 0, k) + 1
print(snap[max(k, 0) : max(k, 0) + length])
