"""Architecture rules the import contracts (pyproject.toml, lint-imports) can't see."""

import pathlib
import re
import unittest

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "prusa_orca"
# Static or importlib imports of OrcaSlicer's embedded module.
ORCA_IMPORT = re.compile(r"^\s*(import orca\b|from orca\b)|import_module\(\s*[\"']orca[\"']", re.M)


class TestLayers(unittest.TestCase):
    def test_only_app_host_loads_orca(self):
        offenders = [
            str(p.relative_to(PACKAGE))
            for p in PACKAGE.rglob("*.py")
            if ORCA_IMPORT.search(p.read_text(encoding="utf-8")) and p != PACKAGE / "app" / "host.py"
        ]
        self.assertEqual(offenders, [], "Only prusa_orca/app/host.py may load the orca module; the rest use host.orca.")

    def test_runtime_code_uses_only_the_standard_library(self):
        # OrcaSlicer runs the plugin on its embedded Python without third-party packages.
        stdlib = {"__future__", *__import__("sys").stdlib_module_names}
        found: set[str] = set()
        for p in PACKAGE.rglob("*.py"):
            for m in re.finditer(r"^\s*(?:import|from)\s+([A-Za-z_]\w*)", p.read_text(encoding="utf-8"), re.M):
                found.add(m.group(1))
        self.assertEqual(sorted(found - stdlib - {"prusa_orca"}), [])


if __name__ == "__main__":
    unittest.main()
