"""The Prusa tab: the webview page, routing its commands to one handler per side tab."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from .. import filament_sync
from ..consistency import preset_mismatch
from ..preset_sync import compare
from ..printers import model_for
from ..tasks import Task, TaskBusy
from ..ui.page_html import PAGES_HTML
from .filament_watch import FilamentWatch
from .host import LOG, PAGE_NAME, install_info, orca
from .orca_state import collect_filament_presets, filament_slots, printer_preset_model, printer_preset_nozzles
from .pages import TABS
from .pages.catalog import recent
from .runtime import runtime
from .views import telemetry_view

ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "assets", "prusa_tab.svg")


class PrusaPage(orca.pages.PagesPluginCapabilityBase):
    """Prusa tab: status, storage, tools, history and settings."""

    def __init__(self) -> None:
        super().__init__()
        self._routes: dict[str, Callable[[dict[str, Any]], None]] = {}
        for tab in TABS:
            self._routes.update(tab(self).handlers())
        self._routes["init"] = self._init
        self._watch = FilamentWatch(runtime(), self._open_finder)

    def _open_finder(self, tool: int) -> None:
        # The plugin API can't switch tabs; the dialog is open when the user opens the Prusa tab.
        self.post_message({"type": "open_finder", "tool": tool})

    def get_name(self) -> str:
        return PAGE_NAME

    def get_ui(self) -> str:
        return PAGES_HTML

    def get_icon(self) -> str:
        # Orca loads it as an SVG and swaps #262E30 for a light colour in dark mode.
        return ICON

    # What the handlers use (pages.base.Page).
    def say(self, text: str) -> None:
        self.post_message({"type": "message", "text": text})

    def push(self) -> None:
        rt = runtime()
        view = telemetry_view(rt)
        if rt.snapshot is not None and rt.snapshot.tools:
            try:
                name, diameters, types = printer_preset_nozzles()
                view["nozzles"] = {"preset": name, "rows": compare(rt.snapshot.tools, diameters, types)}
                slots, colours = filament_slots()
                view["filaments"] = filament_sync.compare(rt.snapshot.tools, rt.presets, slots, colours)
                recent(rt.settings.data_dir).note_slots(slots, rt.presets)
                self._watch.check(rt.snapshot.tools, slots)
            except Exception:
                LOG.exception("could not read the printer preset")
        if rt.snapshot is not None and not rt.identity_error:
            try:
                preset_name, orca_model = printer_preset_model()
                view["preset_notice"] = preset_mismatch(orca_model, preset_name, model_for(rt.snapshot.printer_type))
            except Exception:
                LOG.exception("could not read the printer preset model")
        self.post_message({"type": "telemetry", "data": view})

    def in_background(self, fn: Any, label: str = "", kind: str = "query", resource: str = "") -> None:
        """Run page work as a task; unlabelled work is background (no busy indicator)."""

        def done(task: Task) -> None:
            if task.state != "done":
                self.say(f"{task.label}: {task.error}." if label else f"Error: {task.error}")

        runtime().tasks.submit(label or "page", fn, kind=kind, resource=resource, on_done=done, quiet=not label)

    def _on_task(self, task: Task) -> None:
        # Any thread: the page shows the busy bar right away instead of at the next 3 s poll.
        if not task.quiet:
            self.post_message(
                {
                    "type": "tasks",
                    "data": [t.view() for t in runtime().tasks.running() if not t.quiet],
                    "finished": task.view() if task.state != "running" else None,
                }
            )

    def _init(self, message: dict[str, Any]) -> None:
        rt = runtime()
        if self._on_task not in rt.tasks.listeners:
            rt.tasks.listeners.append(self._on_task)
        try:
            rt.presets = collect_filament_presets()
        except Exception:
            LOG.exception("could not read filament presets")
        rt.start()
        self.post_message({"type": "settings", "data": rt.settings.public_view()})
        self.post_message({"type": "about", "data": install_info()})
        self.push()

    def on_message(self, message: Any) -> None:
        if not isinstance(message, dict):
            return
        command = str(message.get("command") or "")
        handler = self._routes.get(command)
        if handler is None:
            LOG.debug("unknown page command %s", command)
            return
        try:
            handler(message)
        except TaskBusy as exc:
            self.say(f"{exc}.")
        except Exception as exc:
            LOG.exception("page command %s failed", command)
            self.say(f"Error: {exc}")
