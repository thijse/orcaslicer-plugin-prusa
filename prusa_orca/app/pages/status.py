"""Status tab: telemetry, camera snapshot, job buttons and printer controls."""

from __future__ import annotations

import base64
import time
from collections.abc import Mapping
from typing import Any, ClassVar

from ...control import READY_COMMANDS, camera_hint
from ...jsonview import obj
from ..host import LOG
from ..views import CONTROL_COMMANDS, EXTRA_COMMANDS
from .base import TabHandler


class StatusTab(TabHandler):
    COMMANDS: ClassVar[Mapping[str, str]] = {
        "poll": "poll",
        "refresh": "refresh",
        "snapshot": "snapshot",
        "job": "job",
        "control": "control",
    }

    def poll(self, message: dict[str, Any]) -> None:
        self.page.push()

    def refresh(self, message: dict[str, Any]) -> None:
        self.rt.refresh_now()
        self.page.push()

    def snapshot(self, message: dict[str, Any]) -> None:
        self.page.in_background(self._snapshot)

    def _snapshot(self) -> None:
        # Shares the cache the Device tab's camera reads, refreshed in the background.
        try:
            image = self.rt.snapshot_image()
        except Exception as exc:
            hint = camera_hint(False, None, str(exc), self.rt.tokens.logged_in)
            self.page.post_message({"type": "snapshot", "hint": hint})
            raise
        changed_at, error = self.rt.snapshot_status()
        message: dict[str, Any] = {"type": "snapshot"}
        if changed_at:
            message["changed"] = time.strftime("%H:%M:%S", time.localtime(changed_at))
            message["age"] = round(time.time() - changed_at)
        if image:
            message["data"] = "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")
        message["hint"] = camera_hint(bool(image), message.get("age"), error, self.rt.tokens.logged_in)
        self.page.post_message(message)

    def job(self, message: dict[str, Any]) -> None:
        action = str(message.get("action") or "")
        if action in ("pause", "resume", "stop"):
            self.page.in_background(lambda: self._job(action), f"{action.capitalize()} print", kind="job", resource="job")

    def _job(self, action: str) -> None:
        lan = self.lan()
        if lan is None:
            return
        status = lan.job_command(action)
        LOG.info("page job %s: HTTP %s", action, status)
        self.page.say(f"{action.capitalize()} sent." if status in (200, 204) else f"The printer answered HTTP {status}.")
        self.rt.refresh_now()

    def control(self, message: dict[str, Any]) -> None:
        name = str(message.get("name") or "")
        if name not in CONTROL_COMMANDS and name not in EXTRA_COMMANDS and name not in READY_COMMANDS:
            return
        kwargs = obj(message, "kwargs")
        say = self.page.say

        def done(errors: list[str]) -> None:
            if errors:
                say("; ".join(errors))

        if not self.rt.run_commands([(name, kwargs)], done):
            say("Log in to Prusa Connect to control the printer.")
