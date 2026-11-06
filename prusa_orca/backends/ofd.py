"""The Open Filament Database (openfilamentdatabase.org, MIT): one gzipped JSON dump, cached for offline use."""

from __future__ import annotations

import gzip
import json
import os
import time
import urllib.request

from ..jsonview import JsonObj, obj

OFD_HOST = "https://api.openfilamentdatabase.org"
DUMP_URL = f"{OFD_HOST}/json/all.json.gz"
CACHE_FILE = "ofd_all.json.gz"
REFRESH_SECONDS = 24 * 3600  # the database is rebuilt daily


class OfdCache:
    """The dump on disk in the plugin's data folder; refreshed at most once a day, used as is when offline."""

    def __init__(self, data_dir: str, timeout: float = 30.0) -> None:
        self.path = os.path.join(data_dir, CACHE_FILE)
        self.timeout = timeout

    def age_seconds(self) -> float | None:
        try:
            return time.time() - os.path.getmtime(self.path)
        except OSError:
            return None

    def _download(self) -> bytes:
        req = urllib.request.Request(DUMP_URL, headers={"User-Agent": "orca-prusa-plugin"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def load(self) -> tuple[JsonObj, str]:
        """The dump and its state: "ok" (fresh), "cached" (an older copy, the download failed) or "offline" ({})."""
        age = self.age_seconds()
        if age is None or age > REFRESH_SECONDS:
            try:
                raw = self._download()
                obj(json.loads(gzip.decompress(raw)))  # don't overwrite a good copy with a broken download
                tmp = self.path + ".tmp"
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(tmp, "wb") as f:
                    f.write(raw)
                os.replace(tmp, self.path)
            except (OSError, ValueError):
                if age is None:
                    return {}, "offline"
                return self._read(), "cached"
        return self._read(), "ok"

    def _read(self) -> JsonObj:
        try:
            with open(self.path, "rb") as f:
                return obj(json.loads(gzip.decompress(f.read())))
        except (OSError, ValueError):
            return {}
