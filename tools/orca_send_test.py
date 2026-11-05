"""Dev helper: slice a cube in a running Orca and open the Send (upload only) dialog.

  python tools/orca_send_test.py [--press]   --press also clicks Send (uploads a file; never prints)
"""
import re
import sys
import time

from orca_client import connect

o = connect()


def snap(root="all"):
    return o.call_with_text("ui_snapshot", root=root)[1][0]


o.call_raw("run_action", {"id": "orca_command:add_primitive_cube:orca"})
for _ in o.call("get_state")["dialogs"]:
    o.call_raw("dialog_respond", {"button": "OK"})
o.call_raw("slice", {})
o.call_raw("wait", {"for": "idle", "timeout_s": 50})
main = snap("main")
dropdown = re.findall(r"\[(w\d+)\] button \(SideButton\) @\d+,40", main)[-1]
printing = "--print" in sys.argv
mode = "Print" if printing else "Send"
o.call_raw("ui_click", {"target": dropdown})
time.sleep(1)
o.call_raw("ui_click", {"target": {"label": "Print plate" if printing else "Send", "class": "SideButton"}})
time.sleep(1)
main_button = re.findall(rf"\[(w\d+)\] button \"{'Print plate' if printing else 'Send'}\" \(SideButton\)", snap("main"))[-1]
o.call_raw("ui_click", {"target": main_button})
dialog = ""
for _ in range(20):
    time.sleep(1)
    dialog = snap("dialog")
    m = re.search(rf"\[(w\d+)\] button \"{mode}\" \(Button\)(?! \[disabled\])", dialog)
    if m:
        break
print(dialog)
if "--press" in sys.argv:
    print(o.call_raw("ui_click", {"target": m.group(1)}))
