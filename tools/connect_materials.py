"""Dev helper: search Connect's material database, and optionally record one on a tool.

  python tools/connect_materials.py search "Prusament PLA Galaxy Black" [--type PLA]
  python tools/connect_materials.py assign <tool 1-5> <material-uuid>   (label only; no filament moves)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prusa_orca.backends.connect import ConnectBackend, TokenStore  # noqa: E402
from prusa_orca.settings import Settings, default_data_dir  # noqa: E402

parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="cmd", required=True)
s = sub.add_parser("search")
s.add_argument("text")
s.add_argument("--type", default="")
a = sub.add_parser("assign")
a.add_argument("tool", type=int)
a.add_argument("uuid")
args = parser.parse_args()

settings = Settings(default_data_dir())
backend = ConnectBackend(TokenStore(settings.tokens_path), settings.values["connect"]["printer_uuid"])
if args.cmd == "search":
    for item in backend.search_materials(args.text, args.type):
        m = item.get("material") or {}
        print(item["uuid"], "|", (m.get("brand") or {}).get("name"), "|", m.get("name"), "|", m.get("abbreviation"),
              "|", (m.get("primaryColor") or {}).get("colorRgba"), "| custom" if item.get("isCustom") else "")
else:
    backend.assign_material(args.tool - 1, {"uuid": args.uuid})
    print("assigned")
