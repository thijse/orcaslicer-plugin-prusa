"""Orca printer agent: Device tab status, AMS trays, camera, upload/print, controls."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from typing import Any

from .. import gcode_meta, preflight
from ..backends.prusalink import extract_plate_gcode, printer_file_name
from ..control import gcode_to_commands
from ..dialect import build_get_version, build_push_status, limits, tool_mapping_problem
from ..history import new_record
from ..model import PrinterTelemetry
from ..tasks import TaskBusy
from .host import (
    AGENT_ID,
    AGENT_NAME,
    ERR_BUSY,
    ERR_NOT_SUPPORTED,
    LOG,
    OK,
    STAGE_CREATE,
    STAGE_ERROR,
    STAGE_FINISHED,
    STAGE_UPLOAD,
    __version__,
    orca,
)
from .notices import warn
from .orca_state import _preset_names, _project_path, collect_filament_presets
from .runtime import current_runtime, runtime

pa = orca.printer_agent


class PrusaPrinterAgent(pa.PrinterAgentBase):
    """Printer agent: status, tools as AMS trays, camera, upload/print and pause/resume/stop. No motion commands."""

    def __init__(self) -> None:
        super().__init__()
        self._dev_id = ""
        self._sequence = 0
        self._callbacks: dict[str, Any] = {}
        self._connected = False

    def get_name(self) -> str:
        # Orca resolves a preset's stored printer_agent value as a capability name, so the
        # capability name must equal the agent id or saving the preset drops the plugin reference.
        return AGENT_ID

    def get_agent_info(self) -> Any:
        return pa.AgentInfo(AGENT_ID, AGENT_NAME, __version__, "Prusa Buddy printers via PrusaLink and Prusa Connect")

    def on_load(self) -> None:
        runtime()
        LOG.info("agent loaded (v%s)", __version__)

    def on_unload(self) -> None:
        self.disconnect_printer()
        rt = current_runtime()
        if rt is not None:
            rt.stop()

    def on_lifecycle_event(self, event: Any, ctx: Any) -> None:
        if event in (orca.LifecycleEvent.PresetSelected, orca.LifecycleEvent.PresetSaved):
            try:
                runtime().presets = collect_filament_presets()
            except Exception:
                LOG.exception("could not read filament presets")

    # Host callbacks; any of them may be None.
    def _store(self, key: str, fn: Any) -> int:
        self._callbacks[key] = fn
        return OK

    def set_server_callback(self, fn): return self._store("server_error", fn)
    def set_on_ssdp_msg_fn(self, fn): return self._store("ssdp", fn)
    def set_on_printer_connected_fn(self, fn): return self._store("printer_connected", fn)
    def set_on_subscribe_failure_fn(self, fn): return self._store("subscribe_failure", fn)
    def set_on_message_fn(self, fn): return self._store("message", fn)
    def set_on_user_message_fn(self, fn): return self._store("user_message", fn)
    def set_on_local_connect_fn(self, fn): return self._store("local_connect", fn)
    def set_on_local_message_fn(self, fn): return self._store("local_message", fn)
    def set_queue_on_main_fn(self, fn): return self._store("queue_on_main", fn)

    def _emit(self, key: str, *args: Any) -> None:
        fn = self._callbacks.get(key)
        if fn is not None:
            try:
                fn(*args)
            except Exception:
                LOG.exception("host callback %s failed", key)

    def _announce(self) -> None:
        rt = runtime()
        host = rt.settings.values["prusalink"].get("host", "")
        # Orca keys a preset's printer by its print_host, so announce that before any connect.
        dev_id = self._dev_id or host
        if not dev_id:
            return
        printer = rt.settings.values["printer"]
        self._emit("ssdp", json.dumps({
            "dev_name": printer.get("name") or "Prusa", "dev_id": dev_id, "dev_ip": host or dev_id,
            "dev_type": printer.get("model_id", ""), "dev_signal": "0", "connect_type": "lan",
            "bind_state": "free", "sec_link": "secure", "ssdp_version": "v1",
        }))

    def start_discovery(self, start: bool, sending: bool) -> bool:
        if start:
            self._announce()
        return True

    def get_user_selected_machine(self) -> str:
        return self._dev_id

    def set_user_selected_machine(self, dev_id: str) -> int:
        if dev_id:
            self._dev_id = dev_id
        return OK

    def connect_printer(self, params: Any) -> int:
        rt = runtime()
        if not params.dev_id:
            return -1
        self._dev_id = params.dev_id
        if params.host and not rt.settings.values["prusalink"].get("host"):
            rt.settings.update({"prusalink": {"host": params.host}})
            rt.rebuild_backend()
        try:
            rt.presets = collect_filament_presets()
        except Exception:
            LOG.exception("could not read filament presets")
        if self._on_status not in rt.listeners:
            rt.listeners.append(self._on_status)
        rt.start()
        rt.refresh_now()
        LOG.info("connect_printer dev_id=%s host=%s", params.dev_id, params.host)
        return OK

    def disconnect_printer(self) -> int:
        rt = current_runtime()
        if rt is not None and self._on_status in rt.listeners:
            rt.listeners.remove(self._on_status)
        if self._connected:
            self._emit("local_connect", 2, self._dev_id, "disconnected")
        self._connected = False
        return OK

    def _on_status(self, snapshot: PrinterTelemetry | None) -> None:
        if snapshot is None:
            if self._connected:
                self._connected = False
                self._emit("local_connect", 2, self._dev_id, "printer unreachable")
            return
        if not self._connected:
            self._connected = True
            self._announce()
            self._emit("local_connect", 0, self._dev_id, "0")
        self._publish(snapshot)

    def _publish(self, snapshot: PrinterTelemetry) -> None:
        if not self._dev_id:
            return
        self._sequence += 1
        payload = build_push_status(snapshot, self._sequence, runtime().filament_id_for)
        self._emit("local_message", self._dev_id, json.dumps(payload))

    def send_message(self, dev_id, json_str, qos, flag):
        return self.send_message_to_printer(dev_id, json_str, qos, flag)

    def send_message_to_printer(self, dev_id, json_str, qos, flag):
        try:
            msg = json.loads(json_str)
        except ValueError:
            return -1
        rt = runtime()
        if "pushing" in msg:
            if rt.snapshot:
                self._publish(rt.snapshot)
            return OK
        info = msg.get("info") if isinstance(msg, dict) else None
        if isinstance(info, dict) and info.get("command") == "get_version":
            self._sequence += 1
            snapshot = rt.snapshot or PrinterTelemetry(connected=True)
            self._emit("local_message", self._dev_id, json.dumps(build_get_version(snapshot, self._sequence)))
            return OK
        if isinstance(msg, dict) and "system" in msg:
            return OK
        command = (msg.get("print") or {}) if isinstance(msg, dict) else {}
        if command.get("command") == "ams_filament_setting":
            return self._set_tool_material(command)
        if command.get("command") in ("pause", "resume", "stop"):
            return self._job_command(command["command"])
        if command.get("command") == "gcode_line":
            return self._gcode(str(command.get("param") or ""))
        LOG.info("command not supported yet: %s", json_str[:200])
        return ERR_NOT_SUPPORTED

    def _gcode(self, gcode: str) -> int:
        # Orca's temperature, home and jog controls send G-code; Connect runs the equivalent commands.
        snapshot = runtime().snapshot
        nozzle_max, bed_max = limits(snapshot) if snapshot else (290, 120)
        commands = gcode_to_commands(gcode, nozzle_max, bed_max)
        if not commands:
            LOG.info("G-code not supported: %r", gcode[:120])
            return ERR_NOT_SUPPORTED
        return self._run_from_device_tab(commands)

    @staticmethod
    def _run_from_device_tab(commands: list[tuple[str, dict[str, Any]]]) -> int:
        # Orca only sees the return code: busy is refused here, failures and timeouts become notifications.
        try:
            ok = runtime().run_commands(commands, lambda errors: errors and warn("; ".join(errors)))
        except TaskBusy as exc:
            warn(str(exc))
            return ERR_BUSY
        return OK if ok else ERR_NOT_SUPPORTED

    def command_axis_control(self, dev_id, axis, unit, input_val, speed, is_core_xy, supports_mqtt_axis_control,
                             sequence_id, lan_mode):
        # The XL is CoreXY; Orca flips Y and Z for printers it doesn't know, so send the value as clicked.
        distance = round(input_val * unit, 2)
        if axis in ("X", "Y"):
            commands = [("MOVE", {"feedrate": int(speed), axis.lower(): distance})]
        elif axis == "Z":
            commands = [("MOVE_Z", {"feedrate": min(int(speed), 600), "distance": distance})]
        elif axis == "E":
            commands = [("MOVE_E", {"feedrate": int(speed), "length": distance})]
        else:
            return ERR_NOT_SUPPORTED
        return self._run_from_device_tab(commands)

    def _job_command(self, action: str) -> int:
        # Called on the UI thread: talk to the printer in the background.
        rt = runtime()
        lan = rt.backend.lan if rt.backend else None
        if lan is None:
            return -1

        def work() -> None:
            status = lan.job_command(action)
            LOG.info("job %s: HTTP %s", action, status)
            rt.refresh_now()
            if status not in (200, 204):
                raise RuntimeError(f"the printer answered HTTP {status}")

        try:
            rt.tasks.submit(f"{action.capitalize()} print", work, kind="job", resource="job",
                            on_done=lambda t: t.state != "done" and warn(f"{t.label}: {t.error}"))
        except TaskBusy as exc:
            warn(str(exc))
            return ERR_BUSY
        return OK

    def _set_tool_material(self, command: dict) -> int:
        # Orca's AMS slot edit: ams_id/slot_id map to the tool as in build_ams_units (4 tools per unit).
        try:
            tool_index = int(command.get("ams_id", 0)) * 4 + int(command.get("slot_id", 0))
        except (TypeError, ValueError):
            return -1
        rt = runtime()
        preset = next((p for p in rt.presets if p.filament_id and p.filament_id == command.get("tray_info_idx")), None)
        vendor = preset.vendor if preset else ""
        name = preset.name.split("@", 1)[0].strip() if preset else ""
        material_type = str(command.get("tray_type") or (preset.type if preset else ""))
        color = "#" + str(command.get("tray_color") or "")[:6]

        def work() -> None:
            assigned = rt.assign_tool_material(tool_index, vendor, name, material_type, color)
            LOG.info("T%d material set to %s", tool_index + 1, assigned)

        try:
            rt.tasks.submit(f"T{tool_index + 1}: setting the filament", work, kind="command",
                            resource=f"tool-{tool_index + 1}",
                            on_done=lambda t: t.state != "done" and warn(f"{t.label}: {t.error}"))
        except TaskBusy as exc:
            warn(str(exc))
            return ERR_BUSY
        return OK

    def get_filament_sync_mode(self):
        return pa.FilamentSyncMode.Subscription

    def fetch_filament_info(self, dev_id, sync_mode):
        rt = runtime()
        rt.refresh_now()
        if rt.snapshot:
            self._publish(rt.snapshot)
        return rt.snapshot is not None

    def get_camera_stream_mode(self):
        rt = runtime()
        if rt.rtsp_url():
            return pa.CameraStreamMode.RTSP
        if rt.snapshot_url():
            return pa.CameraStreamMode.HTTP_SNAPSHOT
        return pa.CameraStreamMode.None_

    def get_camera_url(self):
        rt = runtime()
        return rt.rtsp_url() or rt.snapshot_url()

    # Upload and print over PrusaLink. Orca only calls these from the user's Send / Print actions.
    def start_send_gcode_to_sdcard(self, params, update_fn, cancel_fn, wait_fn):
        return self._transfer(params, update_fn, cancel_fn, print_after=False)

    def start_local_print(self, params, update_fn, cancel_fn):
        return self._transfer(params, update_fn, cancel_fn, print_after=True)

    def start_local_print_with_record(self, params, update_fn, cancel_fn, wait_fn):
        return self._transfer(params, update_fn, cancel_fn, print_after=True)

    def start_print(self, params, update_fn, cancel_fn, wait_fn):
        return self._transfer(params, update_fn, cancel_fn, print_after=True)

    def start_sdcard_print(self, params, update_fn, cancel_fn):
        return ERR_NOT_SUPPORTED

    def _transfer(self, params: Any, update_fn: Any, cancel_fn: Any, print_after: bool) -> int:
        def stage(step: int, code: int = 0, info: str = "") -> None:
            if update_fn is not None:
                update_fn(step, code, info)

        rt = runtime()
        lan = rt.backend.lan if rt.backend else None
        if lan is None:
            stage(STAGE_ERROR, -1, "PrusaLink host is not set (Prusa tab > Settings)")
            return -1
        # Orca's connection check before a LAN job: answer it without uploading anything.
        if params.project_name == "verify_job":
            return OK if lan.fetch_status() is not None else -1
        problem = tool_mapping_problem(str(params.ams_mapping or ""))
        if print_after and problem:
            stage(STAGE_ERROR, -1, problem)
            LOG.warning("print refused: %s", problem)
            return -1
        # The plugin may write under Orca's data folder without a prompt, not under %TEMP%.
        uploads = os.path.join(rt.settings.data_dir, "uploads")
        os.makedirs(uploads, exist_ok=True)
        work_dir = tempfile.mkdtemp(prefix="job_", dir=uploads)
        plate = int(params.plate_index or 1)
        record = None
        try:
            stage(STAGE_CREATE)
            gcode = extract_plate_gcode(params.filename, plate, work_dir)
            name = printer_file_name(params.project_name or os.path.basename(params.filename), plate)
            meta = gcode_meta.read(gcode)
            check = preflight.check(meta, rt.snapshot, print_after)
            if rt.identity_error:
                check.warnings.insert(0, rt.identity_error)
            if not check.ok:
                LOG.info("pre-flight for %s: %s", name, check.problems + check.warnings)
                if not self._confirm_preflight(check, name):
                    stage(STAGE_ERROR, -1, "; ".join(check.problems + check.warnings))
                    return -1
            record = new_record(name, params.project_name or "", plate, _project_path(), _preset_names(),
                                gcode_meta.summary(meta), print_after, check.problems + check.warnings)
            rt.tracker.handover(record)
            LOG.info("%s %s (%d bytes)", "print" if print_after else "upload", name, os.path.getsize(gcode))
            status = lan.upload(gcode, name, print_after, progress=lambda pct: stage(STAGE_UPLOAD, pct, name),
                                cancelled=(lambda: bool(cancel_fn())) if cancel_fn is not None else None)
        except InterruptedError:
            if record is not None:
                rt.tracker.upload_failed(record, "Cancelled in Orca.")
            return -1
        except Exception as exc:
            LOG.exception("upload failed")
            if record is not None:
                rt.tracker.upload_failed(record, str(exc))
            stage(STAGE_ERROR, -1, str(exc))
            return -1
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
        if status not in (200, 201, 204):
            rt.tracker.upload_failed(record, f"PrusaLink answered HTTP {status}")
            stage(STAGE_ERROR, -1, f"PrusaLink answered HTTP {status}")
            return -1
        rt.refresh_now()
        stage(STAGE_FINISHED, 0, "3")
        return OK

    @staticmethod
    def _confirm_preflight(check: preflight.Preflight, name: str) -> bool:
        """Ask before sending; a blocking problem only informs. Runs on Orca's send worker."""
        text = preflight.message(check, name)
        try:
            if check.problems:
                orca.host.ui.message(text, "Can't send to the printer", "ok", "error")
                return False
            return orca.host.ui.message(text, "Check before printing", "ok_cancel", "warning") == "ok"
        except Exception:
            LOG.exception("pre-flight dialog failed")
            return not check.problems

    def bind_detect(self, dev_ip, sec_link, detect):
        printer = runtime().settings.values["printer"]
        detect.dev_id = self._dev_id or dev_ip
        detect.dev_name = printer.get("name") or "Prusa"
        detect.model_id = printer.get("model_id", "")
        detect.connect_type = "lan"
        detect.bind_state = "free"
        return OK

    # The Python bridge has no fallback for these; without overrides they answer -1.
    def check_cert(self): return OK
    def ping_bind(self, ping_code): return OK
    def bind(self, dev_ip, dev_id, dev_model, sec_link, timezone, improved, update_fn): return OK
    def unbind(self, dev_id): return OK
    def request_bind_ticket(self): return (OK, "")

