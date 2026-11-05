"""Dev CLI for the Prusa plugin, using the settings and Connect login saved by the plugin in Orca.

  python tools/prusa_cli.py status
  python tools/prusa_cli.py files
  python tools/prusa_cli.py upload <file.gcode> [--name NAME]   (never starts a print)
  python tools/prusa_cli.py job pause|resume|stop
  python tools/prusa_cli.py printers                             (Prusa Connect)
"""

from __future__ import annotations

import argparse
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from prusa_orca.backends.connect import ConnectBackend, TokenStore
from prusa_orca.backends.prusalink import PrusaLinkBackend
from prusa_orca.settings import Settings

DEFAULT_DATA_DIR = os.path.expandvars(r"%APPDATA%\OrcaSlicer\orca_plugins\plugin_data\prusa_plugin")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="plugin storage folder")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("files")
    p_upload = sub.add_parser("upload")
    p_upload.add_argument("file")
    p_upload.add_argument("--name", default="")
    p_delete = sub.add_parser("delete")
    p_delete.add_argument("names", nargs="+", help="8.3 names as listed by 'files'")
    p_job = sub.add_parser("job")
    p_job.add_argument("action", choices=["pause", "resume", "stop"])
    sub.add_parser("printers")
    args = parser.parse_args()

    settings = Settings(args.data_dir)
    settings.load()
    if args.command == "printers":
        for p in ConnectBackend(TokenStore(settings.tokens_path), "").list_printers():
            print(p.get("uuid"), p.get("printer_type_name"), p.get("name"))
        return 0

    link = settings.values["prusalink"]
    if not link.get("host"):
        print("PrusaLink host is not set (Prusa tab > Settings)")
        return 1
    lan = PrusaLinkBackend(link["host"], settings.lan_secret, link.get("username", "maker"))

    if args.command == "status":
        t = lan.fetch_status()
        if t is None:
            print(f"Could not reach {lan.host}")
            return 1
        print(f"State: {t.raw_state.value} (phase {t.interpreted_phase.value})")
        print(f"Nozzle: {t.nozzle_temperature} / {t.nozzle_target_temperature} °C")
        print(f"Bed: {t.bed_temperature} / {t.bed_target_temperature} °C")
        if t.job:
            print(f"Job: {t.job.progress_percent}%, {t.job.time_remaining_seconds // 60} min left")
    elif args.command == "files":
        code, body = lan._get(f"/api/v1/files/{lan.storage_path()}/")
        for f in (body or {}).get("children", []):
            print(f.get("name"), f.get("display_name", ""))
    elif args.command == "upload":
        name = args.name or os.path.basename(args.file)
        status = lan.upload(args.file, name, print_after=False, progress=lambda pct: print(f"\r{pct}%", end=""))
        print(f"\nHTTP {status} as {lan.last_upload_name}")
        return 0 if status in (200, 201, 204) else 1
    elif args.command == "delete":
        for name in args.names:
            print(name, "HTTP", lan.delete_file(name))
    elif args.command == "job":
        status = lan.job_command(args.action)
        print(f"HTTP {status}")
        return 0 if status in (200, 204) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
