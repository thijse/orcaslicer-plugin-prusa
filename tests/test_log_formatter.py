import linecache
import logging
import sys
import unittest
from unittest import mock

from prusa_orca.app.host import LogFormatter


class TestLogFormatter(unittest.TestCase):
    def test_traceback_without_reading_source(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            ei = sys.exc_info()
        with mock.patch.object(linecache, "getline", side_effect=AssertionError("read a source file")):
            text = LogFormatter().formatException(ei)
        self.assertIn("test_log_formatter.py", text)
        self.assertIn("RuntimeError: boom", text)
        self.assertNotIn('raise RuntimeError("boom")', text)
        self.assertIsInstance(LogFormatter(), logging.Formatter)


if __name__ == "__main__":
    unittest.main()
