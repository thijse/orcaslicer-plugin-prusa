"""Print history: one record per job, from Orca's handover to the printer's final state.

`PrintTracker.update(telemetry)` is fed every status poll and returns the events to notify about.
A finish or stop takes two polls on the XL (the job disappears and the state changes a poll later),
so the result is decided from the state after the job is gone.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Optional

from .model import PrinterTelemetry, RawPrinterState

MAX_RECORDS = 200
FIRST_LAYER = 2
NEAR_END_SECONDS = 10 * 60
# A handover the printer never picks up is dropped after this long.
PENDING_TIMEOUT = 15 * 60
OPEN_RESULTS = ("printing", "paused", "attention")


def _now() -> float:
    return time.time()


class PrintHistory:
    """Records in a JSON file, newest first."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.records: list[dict[str, Any]] = []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.records = [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.records[:MAX_RECORDS], f, indent=1)
            os.replace(tmp, self.path)

    def add(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.records.insert(0, record)
            del self.records[MAX_RECORDS:]
        self.save()
        return record

    def find(self, record_id: str) -> Optional[dict[str, Any]]:
        return next((r for r in self.records if r.get("id") == record_id), None)

    def remove(self, record_id: str) -> None:
        with self._lock:
            self.records = [r for r in self.records if r.get("id") != record_id]
        self.save()


def new_record(file_name: str, project: str, plate: int, project_path: str, presets: dict[str, Any],
               meta: dict[str, Any], print_after: bool, preflight: list[str]) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:12], "file": file_name, "project": project, "plate": plate,
        "project_path": project_path, "presets": presets, "meta": meta, "preflight": preflight,
        "sent": _now(), "started": None, "ended": None,
        "result": "sending" if print_after else "uploaded",
        "progress": 0.0, "layer": 0, "layers": 0, "z": None, "printing_seconds": 0, "error": "",
        "print_after": print_after,
    }


class PrintTracker:
    """Follows the printer's job and keeps the matching history record up to date."""

    def __init__(self, history: PrintHistory) -> None:
        self.history = history
        self.active: Optional[dict[str, Any]] = None
        self._job_id: Optional[int] = None
        self._flags: set[str] = set()
        self._last: Optional[PrinterTelemetry] = None

    def handover(self, record: dict[str, Any]) -> None:
        """Orca sent a plate; the next job the printer starts with this file belongs to it."""
        self.history.add(record)
        if record["print_after"]:
            self._finish_active("replaced")
            self.active, self._job_id, self._flags = record, None, set()

    def upload_failed(self, record: dict[str, Any], error: str) -> None:
        record.update(result="send_failed", error=error, ended=_now())
        if self.active is record:
            self.active = None
        self.history.save()

    def _finish_active(self, result: str, error: str = "") -> Optional[dict[str, Any]]:
        record = self.active
        if record is None:
            return None
        if record["result"] in ("sending",) + OPEN_RESULTS:
            record.update(result=result, ended=_now(), error=error or record.get("error", ""))
        self.active, self._job_id = None, None
        self.history.save()
        return record

    def _matches(self, record: dict[str, Any], t: PrinterTelemetry) -> bool:
        name = (t.job.display_name or t.job.file_name or "").lower()
        want = record["file"].lower()
        return bool(name) and (name == want or name.startswith(want[:-6]) or want.startswith(name.split("~")[0]))

    def update(self, t: Optional[PrinterTelemetry]) -> list[tuple[str, dict[str, Any]]]:
        """Fold one status poll in; returns (event, record) pairs: started, first_layer, near_end,
        attention, paused, finished, stopped, failed."""
        events: list[tuple[str, dict[str, Any]]] = []
        if t is None or not t.connected:
            return events
        job = t.job
        record = self.active
        if record is None and job.job_id is None:
            # Orca was closed when these prints ended; the outcome is not known.
            for stale in self.history.records:
                if stale["result"] in OPEN_RESULTS:
                    stale.update(result="unknown", ended=stale.get("ended") or _now())
                    self.history.save()
        if job.job_id is not None and self._job_id != job.job_id:
            resumed = next((r for r in self.history.records if r.get("job_id") == job.job_id
                            and r["result"] in OPEN_RESULTS), None)
            if resumed is not None and resumed is not record:
                # Orca restarted during this print: carry on with its record, no new "started".
                self.active, self._job_id, self._flags = resumed, job.job_id, {"first_layer", "near_end"}
                record = resumed
            # A new job on the printer: ours if it is the file we just sent, else one started elsewhere.
            elif record is None or record["result"] != "sending" or not self._matches(record, t):
                if record is not None and record["result"] != "sending":
                    self._finish_active("unknown")
                record = self.history.add(new_record(job.display_name or job.file_name, "", 0, "", {}, {}, True, []))
                record["source"] = "printer"
                self.active, self._flags = record, set()
            if record is not resumed:
                self._job_id = job.job_id
                record.update(result="printing", started=_now(), job_id=job.job_id)
                events.append(("started", record))
        elif record is not None and record["result"] == "sending" and _now() - record["sent"] > PENDING_TIMEOUT:
            self._finish_active("not_started", "The printer didn't start the file.")
            record = None

        if record is not None and self._job_id is not None:
            if job.job_id == self._job_id:
                record.update(progress=round(job.progress_percent, 1), layer=job.layer_num, layers=job.total_layer_num,
                              z=t.axis_z, printing_seconds=job.time_printing_seconds)
                state = t.raw_state
                if state == RawPrinterState.PAUSED and record["result"] != "paused":
                    record["result"] = "paused"
                    events.append(("paused", record))
                elif state == RawPrinterState.ATTENTION and record["result"] != "attention":
                    record["result"] = "attention"
                    msg = t.active_dialog.message if t.active_dialog else ""
                    record["error"] = msg or "The printer needs attention."
                    events.append(("attention", record))
                elif state == RawPrinterState.PRINTING and record["result"] in ("paused", "attention"):
                    record["result"] = "printing"
                if job.layer_num >= FIRST_LAYER and "first_layer" not in self._flags:
                    self._flags.add("first_layer")
                    events.append(("first_layer", record))
                if 0 < job.time_remaining_seconds <= NEAR_END_SECONDS and job.progress_percent >= 50 \
                        and "near_end" not in self._flags:
                    self._flags.add("near_end")
                    events.append(("near_end", record))
                if state == RawPrinterState.ERROR:
                    events.append(("failed", self._finish_active("failed", "The printer reported an error.")))
            elif job.job_id is None:
                # The job is gone; the state tells how it ended (it may lag one poll behind).
                state = t.raw_state
                if state == RawPrinterState.FINISHED or (state in (RawPrinterState.IDLE, RawPrinterState.READY)
                                                         and record["progress"] >= 98):
                    record["progress"] = 100.0
                    events.append(("finished", self._finish_active("finished")))
                elif state == RawPrinterState.STOPPED or state in (RawPrinterState.IDLE, RawPrinterState.READY):
                    events.append(("stopped", self._finish_active("stopped")))
                elif state == RawPrinterState.ERROR:
                    events.append(("failed", self._finish_active("failed", "The printer reported an error.")))
        if events and record is not None and record in self.history.records:
            self.history.save()
        self._last = t
        return events
