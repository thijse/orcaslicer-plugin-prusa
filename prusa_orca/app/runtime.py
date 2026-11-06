"""Shared state of the agent and the tab: settings, backends, poller, tasks, history."""

from __future__ import annotations

import contextlib
import os
import socket
import threading
import time
import urllib.parse

# Imported at load: a first import later compiles stdlib modules, and each bytecode write asks the user for an "open" permission.
from logging.handlers import RotatingFileHandler
from typing import Any

from .. import printers
from ..backends.aggregate import AggregateBackend
from ..backends.connect import ConnectBackend, TokenStore
from ..backends.prusalink import PrusaLinkBackend
from ..backends.snapshot_server import SnapshotServer
from ..history import PrintHistory, PrintTracker
from ..materials import FilamentPreset, match_preset, pick_connect_material, tray_info_idx
from ..model import PrinterTelemetry, ToolState
from ..settings import Settings, default_data_dir
from ..tasks import Task, TaskBusy, TaskRunner
from .host import LOG, LogFormatter, orca
from .notices import command_label, notify


class Runtime:
    """State shared by the agent and the tab: settings, backends, the poller and the last snapshot."""

    def __init__(self, data_dir: str) -> None:
        self.settings = Settings(data_dir)
        self.tokens = TokenStore(self.settings.tokens_path)
        self.lock = threading.Lock()
        self.backend: AggregateBackend | None = None
        self.presets: list[FilamentPreset] = []
        self.pending_verifier = ""
        self.listeners: list[Any] = []
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshots: SnapshotServer | None = None
        self._rtsp_check: tuple[str, float, bool] = ("", 0.0, False)
        self._supported: dict[str, list[str]] | None = None
        self._supported_retry = 0.0
        self.tasks = TaskRunner()
        self._attach_log_file(data_dir)
        self.history = PrintHistory(os.path.join(data_dir, "history.json"))
        self.tracker = PrintTracker(self.history)
        self.listeners.append(self._track)
        self.rebuild_backend()

    @property
    def identity_error(self) -> str:
        backend = self.backend
        return backend.identity_error if backend else ""

    def _identify(self, snapshot: PrinterTelemetry | None) -> None:
        """Keep the printer model in the settings in step with what Connect reports (model, MMU, heads)."""
        if snapshot is None or not snapshot.printer_type or not snapshot.tools or self.identity_error:
            return
        heads = 1 if snapshot.mmu_enabled else len(snapshot.tools)
        found = printers.identify({"printer_type": snapshot.printer_type}, heads, snapshot.mmu_enabled)
        current = self.settings.values["printer"]
        if found and any(current.get(k) != v for k, v in found.items()):
            LOG.info("printer identified as %s (%s)", found["model_name"], found["model_id"])
            self.settings.update({"printer": found})

    def _track(self, snapshot: PrinterTelemetry | None) -> None:
        self._identify(snapshot)
        for event, record in self.tracker.update(snapshot):
            if record is not None:
                LOG.info("print %s: %s", event, record.get("file"))
                notify(event, record)
                if event in ("first_layer", "finished", "stopped", "failed", "attention"):
                    self._keep_snapshot(record, event)

    def _keep_snapshot(self, record: dict[str, Any], event: str) -> None:
        image = self.snapshot_image()
        if not image:
            return
        folder = os.path.join(self.settings.data_dir, "history")
        os.makedirs(folder, exist_ok=True)
        name = f"{record['id']}_{event}.jpg"
        with open(os.path.join(folder, name), "wb") as f:
            f.write(image)
        record.setdefault("snapshots", {})[event] = name
        self.history.save()

    @staticmethod
    def _attach_log_file(data_dir: str) -> None:
        try:
            os.makedirs(data_dir, exist_ok=True)
            handler = RotatingFileHandler(
                os.path.join(data_dir, "prusa_plugin.log"), maxBytes=1_000_000, backupCount=2, encoding="utf-8"
            )
            handler.setFormatter(LogFormatter("%(asctime)s %(threadName)s %(levelname)s %(message)s"))
            LOG.addHandler(handler)
        except OSError:
            LOG.warning("could not open the plugin log file")

    def rebuild_backend(self) -> None:
        values = self.settings.values
        host = values["prusalink"].get("host", "")
        lan = PrusaLinkBackend(host, self.settings.lan_secret, values["prusalink"].get("username", "maker")) if host else None
        cloud = None
        uuid = values["connect"].get("printer_uuid", "")
        if values["connect"].get("enabled", True) and uuid and self.tokens.logged_in:
            cloud = ConnectBackend(self.tokens, uuid)
            debug = values.get("debug") or {}
            cloud.simulate_delay = float(debug.get("connect_delay", 0) or 0)
            cloud.simulate_down = bool(debug.get("connect_down"))
        with self.lock:
            self.backend = AggregateBackend(lan, cloud, float(values["poll"].get("tools_seconds", 30.0)))
            self._supported = None
            self._supported_retry = 0.0
        self._wake.set()

    @property
    def snapshot(self) -> PrinterTelemetry | None:
        backend = self.backend
        return backend.last_snapshot if backend else None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="prusa-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=15)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            backend = self.backend
            if backend is not None:
                try:
                    snapshot = backend.fetch_status()
                except Exception:
                    LOG.exception("status poll failed")
                    snapshot = None
                for listener in list(self.listeners):
                    try:
                        listener(snapshot)
                    except Exception:
                        LOG.exception("status listener failed")
            self._wake.wait(float(self.settings.values["poll"].get("status_seconds", 3.0)))
            self._wake.clear()

    def rtsp_url(self) -> str:
        """The configured RTSP URL while its port answers (the Buddy3D ships with RTSP off), else ""."""
        url = self.settings.values["camera"].get("rtsp_url", "")
        if not url:
            return ""
        now = time.monotonic()
        if self._rtsp_check[0] != url or now - self._rtsp_check[1] > 60:
            parts = urllib.parse.urlsplit(url)
            try:
                socket.create_connection((parts.hostname or "", parts.port or 554), timeout=1).close()
                reachable = True
            except OSError:
                reachable = False
            self._rtsp_check = (url, now, reachable)
        return url if self._rtsp_check[2] else ""

    def snapshot_url(self) -> str:
        """Local URL serving the latest Connect camera snapshot; empty without a Connect printer."""
        backend = self.backend
        cloud = backend.cloud if backend else None
        if cloud is None:
            return ""
        if self._snapshots is None:
            source = {"url": ""}

            def fetch() -> bytes | None:
                current = self.backend.cloud if self.backend else None
                if current is None:
                    return None
                source["url"] = source["url"] or current.snapshot_url()
                return current.fetch_snapshot(source["url"]) if source["url"] else None

            self._snapshots = SnapshotServer(fetch)
            self._snapshots.start()
        return self._snapshots.url

    def snapshot_image(self) -> bytes | None:
        return self._snapshots.image() if self.snapshot_url() and self._snapshots else None

    def snapshot_status(self) -> tuple[float, str]:
        """When the camera picture last changed (0 if never) and the last fetch error."""
        server = self._snapshots
        return (server.changed_at, server.last_error) if server else (0.0, "")

    def supported_commands(self) -> dict[str, list[str]]:
        """Connect commands this printer accepts; {} until the background fetch has answered.

        Called from page polls on Orca's UI thread, so it never waits for the network.
        """
        backend = self.backend
        cloud = backend.cloud if backend else None
        if cloud is None:
            return {}
        if self._supported is None and not self.tasks.busy("supported-commands") and time.time() >= self._supported_retry:

            def fetch() -> None:
                try:
                    self._supported = cloud.supported_commands()
                except Exception:
                    self._supported_retry = time.time() + 60
                    raise

            with contextlib.suppress(TaskBusy):
                self.tasks.submit(
                    "Reading the printer's commands", fetch, kind="query", resource="supported-commands", quiet=True
                )
        return self._supported or {}

    def run_commands(
        self, commands: list[tuple[str, dict[str, Any]]], on_done: Any | None = None, label: str = "", resource: str = ""
    ) -> bool:
        """Send Connect commands in order as one task; False when Connect isn't set up.

        `resource` (default: the first command) blocks a second request for the same control until
        this one is answered or times out. Raises TaskBusy in that case.
        """
        backend = self.backend
        cloud = backend.cloud if backend else None
        if backend is None or cloud is None or not commands:
            return False
        if backend.identity_error:
            if on_done:
                on_done([backend.identity_error])
            return True

        def work() -> list[str]:
            for name, kwargs in commands:
                cloud.command(name, **kwargs)
                LOG.info("Connect %s %s", name, kwargs)
            self.refresh_now()
            return []

        def done(task: Task) -> None:
            if on_done:
                on_done([] if task.state == "done" else [f"{task.label}: {task.error}"])

        self.tasks.submit(
            label or command_label(commands[0][0]), work, kind="command", resource=resource or commands[0][0], on_done=done
        )
        return True

    def refresh_now(self) -> None:
        backend = self.backend
        if backend:
            backend.refresh_tools()
        self._wake.set()

    def filament_id_for(self, tool: ToolState) -> str:
        return tray_info_idx(tool, match_preset(tool, self.presets))

    def assign_tool_material(self, tool_index: int, vendor: str, name: str, material_type: str, color: str) -> str:
        """Record the closest Connect material on a tool (label only); returns what was assigned."""
        backend = self.backend
        cloud = backend.cloud if backend else None
        if backend is None or cloud is None:
            raise RuntimeError("log in to Prusa Connect to change a tool's material")
        if backend.identity_error:
            raise RuntimeError(backend.identity_error)
        nodes = cloud.search_materials(" ".join(x for x in (vendor, name) if x) or material_type, material_type)
        if not nodes and vendor:
            nodes = cloud.search_materials(name or material_type, material_type)
        item = pick_connect_material(nodes, vendor, name, material_type, color)
        if item is None:
            raise RuntimeError(f"no {material_type} material in Connect matches {vendor} {name}".strip())
        snapshot = self.snapshot
        tool = next((t for t in (snapshot.tools if snapshot else []) if t.index == tool_index), None)
        cloud.assign_material(tool.connect_id if tool and tool.connect_id else str(tool_index), item)
        backend.refresh_tools()
        self._wake.set()
        m = item.get("material") or {}
        return f"{(m.get('brand') or {}).get('name', '')} {m.get('name', '')}".strip()


RUNTIME: Runtime | None = None


def runtime() -> Runtime:
    global RUNTIME
    if RUNTIME is None:
        data_dir = default_data_dir()
        if orca is not None:
            try:
                data_dir = orca.host.plugin.storage()
            except Exception:
                LOG.debug("plugin storage unavailable, using %s", data_dir)
        RUNTIME = Runtime(data_dir)
    return RUNTIME


def current_runtime() -> Runtime | None:
    """The runtime if something already started it."""
    return RUNTIME
