"""Screenshots of the Prusa tab for the README, with addresses and ids masked. Assumes the Prusa tab is open.

Usage: python tools/readme_shots.py OUT_DIR
"""

import io
import os
import re
import sys
import time

from orca_client import connect
from PIL import Image

MASK = r"""(function () {
  var rules = [[/\b\d{1,3}(\.\d{1,3}){3}\b/g, '192.168.1.50'], [/rtsp:\/\/[^\s"]+/g, 'rtsp://192.168.1.60/live'],
               [/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, '00000000-0000-0000-0000-000000000000'],
               [/\b\d{5}-\d{16}\b/g, '10000-0000000000000000']];
  function fix(s) { rules.forEach(function (r) { s = s.replace(r[0], r[1]); }); return s; }
  var w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) { var n = w.currentNode, t = fix(n.nodeValue); if (t !== n.nodeValue) n.nodeValue = t; }
  document.querySelectorAll('input[type=text], select option').forEach(function (e) {
    if (e.value) e.value = fix(e.value); if (e.textContent) e.textContent = fix(e.textContent); });
  // File names on the printer can be personal; show neutral demo names instead.
  var demo = ['Benchy_0.2mm_PLA_1h12m.bgcode', 'Spool_holder_0.2mm_PETG_3h05m.bgcode', 'Cable_clips_0.15mm_PLA_42m.bgcode',
              'Multicolour_vase_0.2mm_PLA_5h31m.bgcode', 'Calibration_cube_0.2mm_PLA_18m.bgcode', 'Gear_set_0.15mm_PETG_2h47m.bgcode',
              'Phone_stand_0.2mm_PLA_1h55m.bgcode', 'Drawer_handle_0.2mm_PETG_58m.bgcode', 'Lithophane_0.1mm_PLA_6h20m.bgcode'];
  document.querySelectorAll('#files tr td:nth-child(2)').forEach(function (td, i) { td.textContent = demo[i % demo.length]; });
  // The camera also shows the room; keep the printer recognisable but the background unreadable.
  var cam = document.getElementById('cam'); if (cam) cam.style.filter = 'blur(24px) brightness(.6)';
  return 1;
})()"""

o = connect()
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
ref = re.findall(r'\[(w\d+)\] webview = "about:blank', o.call_with_text("ui_snapshot")[1][0])[0]
for page in ("status", "files", "filament", "history", "settings"):
    o.call("webview_eval", target=ref, script=f"document.querySelector('nav .tab[data-page={page}]').click(); 1")
    time.sleep(3)
    o.call("webview_eval", target=ref, script=MASK)
    time.sleep(0.3)
    _, pngs = o.images("screenshot", target=ref)
    im = Image.open(io.BytesIO(pngs[0])).convert("RGB")
    im.thumbnail((1600, 1600))
    path = os.path.join(out, f"{page}.webp")
    im.save(path, quality=80, method=6)
    print(path, im.size, os.path.getsize(path) // 1024, "KB")
