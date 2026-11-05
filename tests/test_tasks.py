import os
import sys
import threading
import time
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prusa_orca import tasks
from prusa_orca.backends.aggregate import AggregateBackend
from prusa_orca.model import PrinterTelemetry
from prusa_orca.tasks import TaskBusy, TaskRunner, reason


class TestTaskRunner(unittest.TestCase):
    def setUp(self):
        self.runner = TaskRunner()
        self.done = []
        self.finished = threading.Event()

    def on_done(self, task):
        self.done.append((task.state, task.error, task.result))
        self.finished.set()

    def test_done(self):
        task = self.runner.submit("Add", lambda: 42, on_done=self.on_done)
        self.assertTrue(self.finished.wait(2))
        self.assertEqual(self.done, [("done", "", 42)])
        self.assertEqual(task.state, "done")
        self.assertFalse(self.runner.running())

    def test_failure_gets_a_readable_reason(self):
        def fail():
            raise urllib.error.HTTPError("u", 503, "x", {}, None)

        self.runner.submit("Set bed", fail, on_done=self.on_done)
        self.assertTrue(self.finished.wait(2))
        self.assertEqual(self.done[0][:2], ("failed", "Prusa Connect is having problems (HTTP 503)"))

    def test_timeout_releases_the_resource_and_ignores_the_late_answer(self):
        release = threading.Event()
        self.runner.submit("Move", lambda: release.wait(5) and "late", resource="MOVE", timeout=0.6, on_done=self.on_done)
        with self.assertRaises(TaskBusy):
            self.runner.submit("Move", lambda: None, resource="MOVE")
        self.assertTrue(self.finished.wait(3))
        self.assertEqual(self.done[0][:2], ("timeout", "no answer within 0 s"))
        self.assertFalse(self.runner.busy("MOVE"))
        release.set()
        time.sleep(0.2)
        self.assertEqual(len(self.done), 1)  # the late answer doesn't report again

    def test_slow_is_reported(self):
        seen = []
        self.runner.listeners.append(lambda t: seen.append(t.view()["slow"]))
        old = tasks.SLOW_AFTER
        tasks.SLOW_AFTER = 0.3
        try:
            gate = threading.Event()
            self.runner.submit("Home", lambda: gate.wait(2), timeout=5, on_done=self.on_done)
            time.sleep(1.2)
            gate.set()
            self.assertTrue(self.finished.wait(2))
        finally:
            tasks.SLOW_AFTER = old
        self.assertIn(True, seen)

    def test_reasons(self):
        self.assertEqual(
            reason(urllib.error.HTTPError("u", 401, "x", {}, None)), "Prusa Connect refused the request; log in again"
        )
        self.assertEqual(reason(TimeoutError()), "no answer in time")
        self.assertTrue(reason(urllib.error.URLError("getaddrinfo failed")).startswith("can't reach the server"))


class SlowCloud:
    def __init__(self, delay):
        self.delay = delay
        self.calls = 0

    def fetch_telemetry(self):
        self.calls += 1
        time.sleep(self.delay)
        return PrinterTelemetry(connected=True)


class FastLan:
    def fetch_status(self):
        return PrinterTelemetry(connected=True)

    def fetch_info(self):
        return {}


class TestSlowConnectDoesNotBlockLan(unittest.TestCase):
    def test_lan_poll_returns_while_connect_is_slow(self):
        backend = AggregateBackend(FastLan(), SlowCloud(1.0), tools_interval=0)
        start = time.monotonic()
        backend.fetch_status()
        backend.fetch_status()  # Connect still busy: no second request
        self.assertLess(time.monotonic() - start, 0.5)
        self.assertEqual(backend.cloud.calls, 1)


if __name__ == "__main__":
    unittest.main()
