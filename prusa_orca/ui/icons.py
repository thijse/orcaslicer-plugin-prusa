"""Printer art for the Prusa tab.

The illustrations (assets/printer_<family>.webp) were generated with gpt-image-2 by tools/gen_art.py
and keyed with tools/cutout.py; PRINTER_SVG is the fallback when no asset is there.
"""

import base64
import json
import os

FAMILIES = ("xl", "mk4", "mini", "coreone")


def _data_uri(family: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "assets", f"printer_{family}.webp")
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return "data:image/webp;base64," + base64.b64encode(f.read()).decode("ascii")


def printer_image_html() -> str:
    """The XL image, with every family's image in a JSON map the page switches between."""
    art = {f: uri for f in FAMILIES if (uri := _data_uri(f))}
    if not art:
        return PRINTER_SVG
    first = art.get("xl") or next(iter(art.values()))
    return (
        f'<img class="art" id="art" alt="" src="{first}"><script type="application/json" id="art-map">{json.dumps(art)}</script>'
    )


# A 5-toolhead tool changer: frame, gantry, docked heads and the active head on the carriage.
PRINTER_SVG = r"""<svg viewBox="0 0 160 120" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round">
  <rect x="10" y="8" width="140" height="104" rx="6"/>
  <path d="M10 26h140"/>
  <g stroke-width="1.6">
    <rect x="22" y="12" width="14" height="10" rx="2"/><rect x="44" y="12" width="14" height="10" rx="2"/>
    <rect x="102" y="12" width="14" height="10" rx="2"/><rect x="124" y="12" width="14" height="10" rx="2"/>
  </g>
  <path d="M18 54h124"/>
  <rect x="68" y="44" width="24" height="22" rx="3"/>
  <path d="M77 66l3 6 3-6"/>
  <rect x="24" y="92" width="112" height="8" rx="2"/>
  <rect x="62" y="80" width="36" height="12" rx="1" stroke-dasharray="3 2"/>
</svg>"""
