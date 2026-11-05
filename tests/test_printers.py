import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prusa_orca import gcode_meta, preflight, printers  # noqa: E402
from prusa_orca.backends.connect import parse_graphql_tools  # noqa: E402
from prusa_orca.dialect import build_push_status  # noqa: E402
from prusa_orca.model import PrinterTelemetry, RawPrinterState  # noqa: E402
from prusa_orca.preset_sync import compare  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def tool(tid, material="", color="#ff0000ff", active=False, temp=20):
    raw = {"id": tid, "features": {"nozzleDiameter": 0.4, "nozzleHighFlow": False, "nozzleHardened": False},
           "telemetry": {"active": active, "temp": temp, "targetTemp": 0},
           "materialPackageInstance": {"__typename": "ToolMaterialPackageInstanceEmpty", "reason": "x"}}
    if material:
        raw["materialPackageInstance"] = {"__typename": "FFFToolMaterialPackageInstance", "package": {"material": {
            "name": f"{material} Red", "abbreviation": material, "brand": {"name": "Prusament"},
            "primaryColor": {"colorRgba": color}, "type": {"abbreviation": material}}}}
    return raw


def graphql(tools, mmu=None):
    fff = {"tools": tools}
    if mmu is not None:
        fff["hasMmuEnabled"] = mmu
    return {"data": {"printer": {"printer": {"fff": fff}}}}


class TestModels(unittest.TestCase):
    def test_identify(self):
        self.assertEqual(printers.identify({"printer_type": "3.1.0"}, 5, False)["model_id"], "prusa_xl_5t_01")
        self.assertEqual(printers.identify({"printer_type": "3.1.0"}, 1, False)["model_id"], "Prusa XL")
        self.assertEqual(printers.identify({"printer_type": "1.4.1"}, 1, False)["model_id"], "MK4S")
        self.assertEqual(printers.identify({"printer_type": "1.4.1"}, 1, True)["model_id"], "MK4ISMMU3")
        self.assertEqual(printers.identify({"printer_type": "7.1.0"}, 1, True)["model_id"], "Prusa_CORE_One_MMU3")
        self.assertEqual(printers.identify({"printer_type": "7.10.0"}, 8, False)["model_id"], "prusa_coreone_indx_8t")
        self.assertEqual(printers.identify({"printer_type": "2.1.0"}, 1, False)["family"], "mini")
        self.assertEqual(printers.identify({"printer_type": "9.9.9"}, 1, False), {})

    def test_xl_fixture_is_identified(self):
        with open(os.path.join(FIXTURES, "xl_connect_printer.json"), encoding="utf-8") as f:
            detail = json.load(f)["body"]
        self.assertEqual(printers.identify(detail, 5, False)["model"], "XL")


class TestToolIds(unittest.TestCase):
    def test_single_tool(self):
        tools = parse_graphql_tools(graphql([tool("0", "PLA", active=True)]))
        self.assertEqual([(t.label, t.kind, t.connect_id, t.is_active) for t in tools], [("T1", "head", "0", True)])

    def test_mmu_slots(self):
        raws = [tool("0", temp=215)] + [tool(f"0.{i}", "PETG" if i == 2 else "", active=(i == 2)) for i in range(5)]
        tools = parse_graphql_tools(graphql(raws, mmu=True))
        self.assertEqual([t.label for t in tools], [f"Slot {i}" for i in range(1, 6)])
        self.assertEqual(tools[2].connect_id, "0.2")
        self.assertTrue(tools[2].is_active and tools[2].is_loaded and tools[2].material == "PETG")
        self.assertEqual(tools[0].temperature, 215)  # the head's temperature
        self.assertFalse(tools[0].is_loaded)

    def test_mmu_disabled_uses_the_head(self):
        raws = [tool("0", "PLA")] + [tool(f"0.{i}") for i in range(5)]
        tools = parse_graphql_tools(graphql(raws, mmu=False))
        self.assertEqual([(t.label, t.connect_id) for t in tools], [("T1", "0")])

    def test_xl_fixture(self):
        with open(os.path.join(FIXTURES, "xl_graphql_fff_telemetry.json"), encoding="utf-8") as f:
            data = json.load(f)
        tools = parse_graphql_tools(data.get("body", data))
        self.assertEqual([t.connect_id for t in tools], ["0", "1", "2", "3", "4"])


class TestPerModel(unittest.TestCase):
    def test_limits_follow_the_model(self):
        mini = PrinterTelemetry(connected=True, printer_type="2.1.0")
        self.assertEqual(build_push_status(mini, 1)["print"]["nozzle_temp_range"], [0, 280])
        self.assertEqual(build_push_status(mini, 1)["print"]["bed_temp_range"], [0, 100])

    def test_nozzle_sync_compares_the_mmu_head_once(self):
        raws = [tool("0")] + [tool(f"0.{i}") for i in range(5)]
        tools = parse_graphql_tools(graphql(raws, mmu=True))
        self.assertEqual(len(compare(tools, "0.4", "brass")), 1)

    def test_preflight_model_mismatch(self):
        meta = gcode_meta.parse_text("; filament_type = PLA\n; printer_model = Prusa MK4S HF\n")
        t = PrinterTelemetry(connected=True, raw_state=RawPrinterState.IDLE, printer_type="2.1.0",
                             tools=parse_graphql_tools(graphql([tool("0", "PLA")])))
        self.assertTrue(any("sliced for Prusa MK4S HF, but the printer is a Prusa MINI" in w
                            for w in preflight.check(meta, t, True).warnings))
        t.printer_type = "1.4.1"
        t.tools[0].high_flow = True
        self.assertTrue(preflight.check(meta, t, True).ok)

    def test_preflight_matches_variants(self):
        for sliced, ptype in (("Prusa XL 5T", "3.1.0"), ("Prusa CORE One MMU3", "7.1.0"), ("Prusa MINIIS", "2.1.0"),
                              ("Prusa MK4 MMU3", "1.4.0"), ("Prusa CORE One INDX 4T", "7.10.0")):
            meta = gcode_meta.parse_text(f"; printer_model = {sliced}\n")
            t = PrinterTelemetry(connected=True, raw_state=RawPrinterState.IDLE, printer_type=ptype)
            self.assertFalse(preflight.check(meta, t, True).warnings, sliced)


if __name__ == "__main__":
    unittest.main()
