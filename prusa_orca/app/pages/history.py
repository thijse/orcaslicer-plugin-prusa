"""History tab: past prints, their snapshots and projects."""

from __future__ import annotations

import base64
import contextlib
import os
import webbrowser
from collections.abc import Mapping
from typing import Any, ClassVar

from .base import TabHandler


class HistoryTab(TabHandler):
    COMMANDS: ClassVar[Mapping[str, str]] = {
        "history": "history",
        "history_shot": "shot",
        "history_remove": "remove",
        "history_open": "open",
    }

    def _folder(self) -> str:
        return os.path.join(self.rt.settings.data_dir, "history")

    def history(self, message: dict[str, Any]) -> None:
        self.page.post_message({"type": "history", "data": self.rt.history.records})

    def shot(self, message: dict[str, Any]) -> None:
        name = os.path.basename(str(message.get("name") or ""))
        path = os.path.join(self._folder(), name)
        if name and os.path.isfile(path):
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            self.page.post_message({"type": "history_shot", "name": name, "data": "data:image/jpeg;base64," + data})

    def remove(self, message: dict[str, Any]) -> None:
        record = self.rt.history.find(str(message.get("id") or ""))
        if record is not None:
            for name in (record.get("snapshots") or {}).values():
                with contextlib.suppress(OSError):
                    os.remove(os.path.join(self._folder(), os.path.basename(name)))
            self.rt.history.remove(record["id"])
        self.history(message)

    def open(self, message: dict[str, Any]) -> None:
        record = self.rt.history.find(str(message.get("id") or ""))
        path = (record or {}).get("project_path") or ""
        if path and os.path.isfile(path):
            # The plugin API can't open a project in Orca, so show the file to drag in or double-click.
            webbrowser.open("file:///" + os.path.dirname(path).replace("\\", "/"))
        else:
            self.page.say("The project file is no longer there.")
