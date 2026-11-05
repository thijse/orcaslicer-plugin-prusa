"""Settings tab: PrusaLink host, Prusa Connect login and printer, notifications."""

from __future__ import annotations

import webbrowser
from collections.abc import Mapping
from typing import Any, ClassVar

from ...backends.connect import ConnectAuthError, ConnectBackend, build_authorize_url, code_from_redirect, generate_pkce_pair
from ..notices import notify
from .base import TabHandler


class SettingsTab(TabHandler):
    COMMANDS: ClassVar[Mapping[str, str]] = {
        "save_settings": "save",
        "login_start": "login_start",
        "login_finish": "login_finish",
        "logout": "logout",
        "fill_from_connect": "fill_from_connect",
        "list_printers": "list_printers",
        "choose_printer": "choose_printer",
        "test_notify": "test_notify",
    }

    def send_settings(self) -> None:
        self.page.post_message({"type": "settings", "data": self.rt.settings.public_view()})

    def save(self, message: dict[str, Any]) -> None:
        self.rt.settings.update(message.get("patch") or {})
        if message.get("quiet"):
            return
        self.rt.rebuild_backend()
        self.send_settings()
        self.page.say("Settings saved.")

    def login_start(self, message: dict[str, Any]) -> None:
        verifier, challenge = generate_pkce_pair()
        self.rt.pending_verifier = verifier
        webbrowser.open(build_authorize_url(challenge))
        self.page.say(
            "Log in in your browser. The last step tries to open PrusaSlicer: cancel that, "
            "copy the prusaslicer://login?code=... address and paste it above."
        )

    def login_finish(self, message: dict[str, Any]) -> None:
        rt = self.rt
        code = code_from_redirect(str(message.get("code") or ""))
        if not code or not rt.pending_verifier:
            self.page.say("Press Log in first, then paste the redirect address.")
            self.page.post_message(
                {"type": "wizard", "step": "login_failed", "text": "open the login page first, then paste the address it ends on"}
            )
            return
        verifier, rt.pending_verifier = rt.pending_verifier, ""

        def work() -> None:
            try:
                rt.tokens.exchange_code(code, verifier)
                rt.rebuild_backend()
                self.page.say("Logged in to Prusa Connect.")
                self.page.post_message({"type": "wizard", "step": "logged_in"})
            except ConnectAuthError as exc:
                self.page.say(f"Login failed: {exc}. Codes are single-use; press Log in again.")
                self.page.post_message({"type": "wizard", "step": "login_failed", "text": str(exc)})

        self.page.in_background(work, "Logging in to Prusa Connect", resource="login")

    def logout(self, message: dict[str, Any]) -> None:
        self.rt.tokens.clear()
        self.rt.rebuild_backend()
        self.page.say("Logged out of Prusa Connect.")
        self.page.push()

    def list_printers(self, message: dict[str, Any]) -> None:
        def work() -> None:
            if not self.rt.tokens.logged_in:
                self.page.say("Log in to Prusa Connect first.")
                return
            self.page.post_message({"type": "printers", "data": ConnectBackend(self.rt.tokens, "").list_printers()})

        self.page.in_background(work, "Listing printers", resource="list-printers")

    def choose_printer(self, message: dict[str, Any]) -> None:
        self.rt.settings.update({"connect": {"printer_uuid": str(message.get("uuid") or "")}})
        self.rt.rebuild_backend()
        self.send_settings()
        self.fill_from_connect(message)

    def fill_from_connect(self, message: dict[str, Any]) -> None:
        rt = self.rt
        uuid = rt.settings.values["connect"].get("printer_uuid", "")
        if not rt.tokens.logged_in:
            self.page.say("Log in to Prusa Connect first.")
            return

        def work() -> None:
            try:
                if not uuid:
                    self.page.say("Enter the printer UUID first (Connect > printer > Settings).")
                    return
                filled = rt.settings.fill_from_connect(ConnectBackend(rt.tokens, uuid).fetch_printer())
                rt.rebuild_backend()
                self.send_settings()
                self.page.say("Filled: " + ", ".join(filled) if filled else "Nothing to fill; settings already set.")
            except Exception as exc:
                self.page.say(f"Could not read the printer from Connect: {exc}")

        self.page.in_background(work, "Reading the printer from Connect", resource="fill")

    def test_notify(self, message: dict[str, Any]) -> None:
        self.page.in_background(lambda: notify("finished", {"file": "Test print", "progress": 100}))
