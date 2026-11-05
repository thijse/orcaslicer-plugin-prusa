"""Dev helper: screenshot Orca's main window per tab, as PNG plus a small JPEG for review.

  python tools/orca_shot.py OUT_DIR [tab ...]     tabs: monitor, printer_web, prusa, prepare, preview (default: monitor prusa)
"""
import os
import re
import sys
import time

from orca_client import connect

o = connect()
# Tabs without a go_to_tab id are reached through their tab-bar button.
BUTTONS = {"printer_web": "Device (Web)", "prusa": "Prusa"}

out_dir = sys.argv[1]
os.makedirs(out_dir, exist_ok=True)
for tab in sys.argv[2:] or ["monitor", "prusa"]:
    if tab in BUTTONS:
        snap = o.call_with_text("ui_snapshot", root="main")[1][0]
        ref = re.search(rf"\[(w\d+)\] button \"{re.escape(BUTTONS[tab])}\" \(Button\)", snap).group(1)
        o.call_raw("ui_click", {"target": ref})
    else:
        o.call_raw("run_action", {"id": "orca_command:go_to_tab:orca", "param": tab})
    time.sleep(4)
    _, pngs = o.images("screenshot", target="window")
    path = os.path.join(out_dir, f"{tab}.png")
    with open(path, "wb") as f:
        f.write(pngs[0])
    try:
        from PIL import Image

        img = Image.open(path).convert("RGB")
        img.thumbnail((1400, 1400))
        img.save(os.path.join(out_dir, f"{tab}_small.jpg"), quality=80)
    except ImportError:
        pass
    print(path)
