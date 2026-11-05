"""Storage tab: files on the printer's drive, thumbnails and printing a stored file."""

from __future__ import annotations

import base64
import os
import re
import urllib.parse
from collections.abc import Mapping
from typing import Any, ClassVar

from ... import gcode_meta, preflight
from ..host import LOG
from .base import TabHandler


class StorageTab(TabHandler):
    COMMANDS: ClassVar[Mapping[str, str]] = {"list_files": "list_files", "thumbnail": "thumbnail", "print_file": "print_file"}

    def list_files(self, message: dict[str, Any]) -> None:
        self.page.in_background(self._list_files, "Reading printer storage", resource="files")

    def _list_files(self) -> None:
        lan = self.lan()
        if lan is not None:
            self.page.post_message(
                {
                    "type": "files",
                    "data": [
                        {"name": f.get("name"), "display_name": f.get("display_name"), "time": f.get("m_timestamp")}
                        for f in lan.list_files()
                    ],
                }
            )

    def thumbnail(self, message: dict[str, Any]) -> None:
        name = str(message.get("file") or "")
        self.page.in_background(lambda: self._thumbnail(name))

    def _thumbnail(self, name: str) -> None:
        lan = self.lan()
        if lan is None or not name:
            return
        # The XL takes 5-12 s per thumbnail, so keep them; file names are unique 8.3 names on the drive.
        cache = os.path.join(self.rt.settings.data_dir, "thumbs", re.sub(r"[^A-Za-z0-9_.~-]", "_", name))
        if os.path.exists(cache):
            with open(cache, "rb") as f:
                image = f.read()
        else:
            image = lan.fetch_bytes(f"/thumb/l/{lan.storage_path()}/{urllib.parse.quote(name)}")
            if image:
                os.makedirs(os.path.dirname(cache), exist_ok=True)
                with open(cache, "wb") as f:
                    f.write(image)
        kind = "png" if image and image[:4] == b"\x89PNG" else "jpeg"
        # Answer even without an image: the page fetches thumbnails one at a time.
        self.page.post_message(
            {
                "type": "thumbnail",
                "file": name,
                "data": f"data:image/{kind};base64," + base64.b64encode(image).decode("ascii") if image else "",
            }
        )

    def print_file(self, message: dict[str, Any]) -> None:
        name = str(message.get("name") or "")
        if not message.get("confirmed"):
            # The tools may have changed since the file was sent: check it against the record Orca kept.
            record = next((r for r in self.rt.history.records if r.get("file") == name and r.get("meta")), None)
            meta = gcode_meta.from_summary(record["meta"]) if record else None
            check = preflight.check_reprint(meta, self.rt.snapshot) if meta else preflight.Preflight()
            if self.rt.identity_error:
                check.warnings.insert(0, self.rt.identity_error)
            if not check.ok:
                self.page.post_message(
                    {
                        "type": "confirm_print",
                        "name": name,
                        "blocked": bool(check.problems),
                        "text": preflight.message(check, name, "print"),
                    }
                )
                return
        self.page.in_background(lambda: self._print_file(name), "Starting print", kind="job", resource="job")

    def _print_file(self, name: str) -> None:
        lan = self.lan()
        if lan is None or not name:
            return
        status = lan.print_file(name)
        LOG.info("print file %s: HTTP %s", name, status)
        self.page.say(
            "Print started."
            if status in (200, 201, 204)
            else "The printer is busy."
            if status == 409
            else f"The printer answered HTTP {status}."
        )
        self.rt.refresh_now()
