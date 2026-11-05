"""Screenshot each Prusa tab subpage (Orca window) as small JPEGs for review.

Usage: python tools/shot_pages.py OUT_DIR [status files filament settings]
Assumes the Prusa tab is open.
"""

import io
import json
import os
import re
import sys
import time

from PIL import Image

sys.path.insert(0, os.path.join(os.environ.get("ORCASLICER_SRC", r"D:\Github\OrcaSlicer"), "tools", "mcp"))
from orca_mcp import OrcaMcp  # noqa: E402

info = json.load(open(os.path.join(os.environ["APPDATA"], "OrcaSlicer", "mcp", "server.json")))
o = OrcaMcp(port=int(info["port"]), token=info["token"])
out = sys.argv[1]
pages = sys.argv[2:] or ["status", "settings"]
os.makedirs(out, exist_ok=True)
ref = re.findall(r'\[(w\d+)\] webview = "about:blank', o.call_with_text("ui_snapshot")[1][0])[0]
for page in pages:
    o.call("webview_eval", target=ref, script=f"document.querySelector('nav .tab[data-page={page}]').click(); 1")
    time.sleep(3)
    _, pngs = o.images("screenshot", target="window")
    im = Image.open(io.BytesIO(pngs[0])).convert("RGB")
    im.thumbnail((1800, 1800))
    path = os.path.join(out, f"page_{page}.jpg")
    im.save(path, quality=82)
    print(path, im.size)
