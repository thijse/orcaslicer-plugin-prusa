"""Setup wizard: log in to Prusa Connect, pick the printer, take its address and keys, test PrusaLink."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from ...backends.connect import ConnectBackend
from ...backends.prusalink import PrusaLinkBackend
from ...setup_wizard import propose
from .base import TabHandler


class SetupWizard(TabHandler):
    COMMANDS: ClassVar[Mapping[str, str]] = {
        "wizard_state": "state",
        "wizard_printers": "printers",
        "wizard_read": "read",
        "wizard_apply": "apply",
        "wizard_test": "test",
    }

    def _post(self, step: str, **data: Any) -> None:
        self.page.post_message({"type": "wizard", "step": step, **data})

    def state(self, message: dict[str, Any]) -> None:
        values = self.rt.settings.values
        self._post(
            "state",
            logged_in=self.rt.tokens.logged_in,
            configured=bool(values["prusalink"].get("host") and self.rt.settings.lan_secret),
        )

    def printers(self, message: dict[str, Any]) -> None:
        def work() -> None:
            if not self.rt.tokens.logged_in:
                self._post("state", logged_in=False, configured=False)
                return
            self._post("printers", printers=ConnectBackend(self.rt.tokens, "").list_printers())

        self.page.in_background(work, "Listing your printers", resource="list-printers")

    def read(self, message: dict[str, Any]) -> None:
        uuid = str(message.get("uuid") or "")

        def work() -> None:
            cloud = ConnectBackend(self.rt.tokens, uuid)
            detail = cloud.fetch_printer()
            try:
                cameras = cloud.list_cameras()
            except Exception:
                cameras = []
            proposal = propose(detail, cameras)
            self._post(
                "proposal", uuid=uuid, patch=proposal.patch, found=proposal.found, missing=proposal.missing, notes=proposal.notes
            )

        self.page.in_background(work, "Reading the printer from Prusa Connect", resource="fill")

    def apply(self, message: dict[str, Any]) -> None:
        patch = message.get("patch") or {}
        password = str(message.get("password") or "")
        if password:
            patch.setdefault("prusalink", {})["password"] = password
        self.rt.settings.update(patch)
        self.rt.rebuild_backend()
        self.page.post_message({"type": "settings", "data": self.rt.settings.public_view()})
        self.test(message)

    def test(self, message: dict[str, Any]) -> None:
        settings = self.rt.settings
        host = settings.values["prusalink"].get("host", "")

        def work() -> None:
            if not host:
                self._post("tested", ok=False, text="No PrusaLink address yet.")
                return
            lan = PrusaLinkBackend(host, settings.lan_secret, settings.values["prusalink"].get("username", "maker"))
            ok, text = lan.check()
            if ok:
                self.rt.refresh_now()
                text = f"Connected to {text} over PrusaLink."
            self._post("tested", ok=ok, text=text)

        self.page.in_background(work, "Testing PrusaLink", resource="wizard-test")
