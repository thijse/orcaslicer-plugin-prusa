import os
import sys
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prusa_orca.backends.snapshot_server import SnapshotServer  # noqa: E402


class TestSnapshotServer(unittest.TestCase):
    def test_serves_cached_image_only_on_its_path(self):
        calls = []

        def fetch():
            calls.append(1)
            return b"\xff\xd8\xff-jpeg"

        server = SnapshotServer(fetch, interval=60)
        url = server.start()
        try:
            for _ in range(50):
                if server.image():
                    break
                time.sleep(0.02)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(3):
                with opener.open(url + "?_orca_frame=1", timeout=5) as resp:
                    self.assertEqual(resp.read(), b"\xff\xd8\xff-jpeg")
                    self.assertEqual(resp.headers["Content-Type"], "image/jpeg")
            self.assertEqual(len(calls), 1)
            with self.assertRaises(urllib.error.HTTPError):
                opener.open(url.rsplit("/", 1)[0] + "/other.jpg", timeout=5)
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
