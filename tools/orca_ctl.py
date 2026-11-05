"""Dev helper for driving OrcaSlicer over MCP.

  python tools/orca_ctl.py answer-all <Yes|No>   press a button on every open dialog
  python tools/orca_ctl.py click <ref>
"""
import json
import sys
import time

from orca_client import connect

o = connect()

cmd = sys.argv[1]
if cmd == "answer-all":
    for _ in range(50):
        dialogs = o.call("get_state")["dialogs"]
        if not dialogs:
            break
        d = dialogs[-1]
        print("answer", sys.argv[2], "->", d["title"], "|", d.get("message", "")[:160].replace("\n", " / "))
        o.call("dialog_respond", button=sys.argv[2])
        time.sleep(0.5)
elif cmd == "click":
    print(json.dumps(o.call("ui_click", ref=sys.argv[2]), indent=1)[:2000])
