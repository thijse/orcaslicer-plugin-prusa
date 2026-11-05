"""Read-only print logger: one JSON line per poll to tests/fixtures/raw/printing/watch_<time>.jsonl until the job ends."""

from __future__ import annotations

import json
import os
import sys
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

from prusa_orca.backends.aggregate import merge
from prusa_orca.backends.connect import ConnectBackend, TokenStore
from prusa_orca.backends.prusalink import PrusaLinkBackend
from prusa_orca.settings import Settings

DATA_DIR = os.path.expandvars(r"%APPDATA%\OrcaSlicer\orca_plugins\plugin_data\prusa_plugin")
INTERVAL = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0


def main() -> None:
    settings = Settings(DATA_DIR)
    settings.load()
    link = settings.values["prusalink"]
    lan = PrusaLinkBackend(link["host"], settings.lan_secret, link.get("username", "maker"))
    cloud = ConnectBackend(TokenStore(settings.tokens_path), settings.values["connect"]["printer_uuid"])
    out_dir = os.path.join(_REPO_ROOT, "tests", "fixtures", "raw", "printing")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, time.strftime("watch_%H%M%S.jsonl"))
    print(path, flush=True)
    seen_job = False
    while True:
        row: dict = {"t": round(time.time())}
        try:
            t = merge(lan.fetch_status(), cloud.fetch_telemetry())
            if t is not None:
                row.update(
                    state=t.raw_state.value,
                    phase=t.interpreted_phase.value,
                    z=t.axis_z,
                    bed=[t.bed_temperature, t.bed_target_temperature],
                    progress=t.job.progress_percent,
                    left=t.job.time_remaining_seconds,
                    layer=[t.job.layer_num, t.job.total_layer_num],
                    active=t.active_tool,
                    tools=[[x.temperature, x.target_temperature, x.is_active] for x in t.tools],
                )
                seen_job = seen_job or t.job.job_id is not None
        except Exception as exc:
            row["error"] = str(exc)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        print(row, flush=True)
        if seen_job and row.get("state") in ("FINISHED", "STOPPED", "IDLE", "ERROR"):
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
