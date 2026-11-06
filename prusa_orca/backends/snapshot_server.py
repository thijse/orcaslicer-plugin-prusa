"""Serves the latest Prusa Connect camera snapshot on localhost for Orca's HTTP-snapshot camera mode.

Orca polls the URL several times a second; the server answers from a cache that a background thread
refreshes, so Connect is only asked every few seconds.
"""

from __future__ import annotations

import http.server
import logging
import secrets
import threading
import time
from collections.abc import Callable
from typing import Any

LOG = logging.getLogger("prusa_orca.snapshot")


class SnapshotServer:
    def __init__(self, fetch: Callable[[], bytes | None], interval: float = 10.0) -> None:
        self._fetch = fetch
        self._interval = interval
        self._image: bytes | None = None
        # When the picture last changed (Connect may keep serving the same one) and why the last fetch failed.
        self.changed_at = 0.0
        self.last_error = ""
        self._lock = threading.Lock()
        self._stop = threading.Event()
        # An unguessable path: other local programs can't read the camera by guessing the port.
        self._path = "/" + secrets.token_urlsafe(16) + ".jpg"
        self._httpd: http.server.ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        if self._httpd is None:
            return ""
        return f"http://127.0.0.1:{self._httpd.server_address[1]}{self._path}"

    def image(self) -> bytes | None:
        with self._lock:
            return self._image

    def start(self) -> str:
        if self._httpd is not None:
            return self.url
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                image = server.image() if self.path.split("?", 1)[0] == server._path else None
                if image is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(image)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(image)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.daemon_threads = True
        threading.Thread(target=self._httpd.serve_forever, name="prusa-snapshot-http", daemon=True).start()
        threading.Thread(target=self._refresh_loop, name="prusa-snapshot-fetch", daemon=True).start()
        return self.url

    def stop(self) -> None:
        self._stop.set()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def _refresh_loop(self) -> None:
        while not self._stop.is_set():
            try:
                image = self._fetch()
                if image:
                    with self._lock:
                        if image != self._image:
                            self.changed_at = time.time()
                        self._image = image
                self.last_error = "" if image else "Prusa Connect has no picture from the camera"
            except Exception as exc:
                self.last_error = str(exc)
                LOG.debug("snapshot fetch failed: %s", exc)
            self._stop.wait(self._interval)
