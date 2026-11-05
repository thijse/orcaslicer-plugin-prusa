"""The Orca-facing layer imports and routes every page command, with a stub `orca` module."""

import importlib
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _stub_orca() -> types.ModuleType:
    class Base:
        def __init__(self, *args, **kwargs):
            self.posted = []

        def post_message(self, message):
            self.posted.append(message)

    orca = types.ModuleType("orca")
    orca.printer_agent = types.SimpleNamespace(
        PrinterAgentBase=Base,
        AgentInfo=lambda *a: a,
        FilamentSyncMode=types.SimpleNamespace(Subscription=1),
        CameraStreamMode=types.SimpleNamespace(RTSP=1, HTTP_SNAPSHOT=2, None_=0),
    )
    orca.pages = types.SimpleNamespace(PagesPluginCapabilityBase=Base)
    orca.register_capability = lambda cls: None
    orca.request_permissions = lambda **kw: None
    orca.plugin = lambda cls: cls
    orca.base = object
    return orca


class TestAppWiring(unittest.TestCase):
    def setUp(self):
        self._saved = {k: v for k, v in sys.modules.items() if k == "orca" or k.startswith("prusa_orca.app")}
        for k in list(self._saved):
            del sys.modules[k]
        sys.modules["orca"] = _stub_orca()

    def tearDown(self):
        for k in [k for k in sys.modules if k == "orca" or k.startswith("prusa_orca.app")]:
            del sys.modules[k]
        sys.modules.update(self._saved)

    def test_page_routes_every_command_the_html_sends(self):
        import re

        page_mod = importlib.import_module("prusa_orca.app.page")
        importlib.import_module("prusa_orca.app.agent")
        from prusa_orca.ui.page_html import PAGES_HTML

        page = page_mod.PrusaPage()
        sent = set(re.findall(r"command:\s*'(\w+)'", PAGES_HTML))
        self.assertTrue(sent, "no commands found in the page")
        self.assertEqual(sorted(sent - set(page._routes)), [])
        self.assertTrue(os.path.isfile(page.get_icon()))

    def test_command_tables_point_at_methods(self):
        from prusa_orca.app.pages import TABS

        for tab in TABS:
            for method in tab.COMMANDS.values():
                self.assertTrue(callable(getattr(tab, method, None)), f"{tab.__name__}.{method}")


if __name__ == "__main__":
    unittest.main()
