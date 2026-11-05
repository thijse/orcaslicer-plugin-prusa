"""Tiny dev helper: call OrcaSlicer's MCP server. Usage: python tools/orca.py <tool> '<json args>'"""
import json
import os
import sys

from orca_client import connect

o = connect()
args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
r = o.call_raw(sys.argv[1], args)
try:
    text = r["content"][0]["text"]
    out = json.dumps(json.loads(text), indent=1, ensure_ascii=False)
except (KeyError, IndexError, TypeError, ValueError):
    out = json.dumps(r, indent=1, ensure_ascii=False)
print(out[: int(os.environ.get("MAXOUT", "6000"))])
