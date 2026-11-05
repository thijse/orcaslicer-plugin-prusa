"""Shared plumbing for the Prusa tab's handlers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, ClassVar, Protocol

from ...backends.prusalink import PrusaLinkBackend
from ..runtime import Runtime, runtime


class Page(Protocol):
    """What a handler may use of the page: messages to the webview and background work."""

    def post_message(self, message: dict[str, Any]) -> None: ...
    def say(self, text: str) -> None: ...
    def push(self) -> None: ...
    def in_background(self, fn: Callable[[], Any], label: str = "", kind: str = "query", resource: str = "") -> None: ...


class TabHandler:
    """Commands of one side tab. COMMANDS maps a page command to a method taking the message."""

    COMMANDS: ClassVar[Mapping[str, str]] = {}

    def __init__(self, page: Page) -> None:
        self.page = page

    @property
    def rt(self) -> Runtime:
        return runtime()

    def lan(self) -> PrusaLinkBackend | None:
        lan = self.rt.backend.lan if self.rt.backend else None
        if lan is None:
            self.page.say("Set the PrusaLink host in Settings first.")
        return lan

    def handlers(self) -> dict[str, Callable[[dict[str, Any]], None]]:
        return {command: getattr(self, method) for command, method in self.COMMANDS.items()}
