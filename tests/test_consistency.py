import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prusa_orca import consistency, gcode_meta, preflight, printers  # noqa: E402
from prusa_orca.backends.aggregate import AggregateBackend  # noqa: E402
from prusa_orca.model import PrinterTelemetry, RawPrinterState, ToolState  # noqa: E402


def printer(ptype="3.1.0", **tool):
    return PrinterTelemetry(connected=True, raw_state=RawPrinterState.IDLE, printer_type=ptype,
                            tools=[ToolState(index=0, tool_number=1, material="PLA", **tool)])


def warnings(text, telemetry):
    return preflight.check(gcode_meta.parse_text(text), telemetry, True).warnings


class TestSerial(unittest.TestCase):
    def test_mismatch(self):
        self.assertIn("different printers", consistency.serial_mismatch("10381-1", "10381-2"))
        self.assertEqual(consistency.serial_mismatch("10381-1", " 10381-1 "), "")
        self.assertEqual(consistency.serial_mismatch("", "10381-2"), "")  # unknown: no claim

    def test_aggregate_drops_the_other_printers_data(self):
        class Lan:
            def fetch_status(self):
                return PrinterTelemetry(connected=True, raw_state=RawPrinterState.IDLE, source="lan")

            def fetch_info(self):
                return {"serial": "10381-LAN"}

        backend = AggregateBackend(Lan(), None)
        backend._cloud_snapshot = PrinterTelemetry(serial_number="10381-CLOUD", tools=printer().tools)
        snapshot = backend.fetch_status()
        self.assertTrue(backend.identity_error)
        self.assertEqual(snapshot.tools, [])
        self.assertEqual(snapshot.serial_number, "10381-LAN")
        backend._cloud_snapshot.serial_number = "10381-LAN"
        self.assertEqual(len(backend.fetch_status().tools), 1)


class TestPresetNotice(unittest.TestCase):
    def test_notice(self):
        xl = printers.model_for("3.1.0")
        self.assertEqual(consistency.preset_mismatch("Prusa XL 5T", "Prusa XL 5T 0.4 nozzle", xl), "")
        self.assertIn("is for the Prusa MK4S", consistency.preset_mismatch("Prusa MK4S", "Prusa MK4S 0.4", xl))
        self.assertIn("not a Prusa printer", consistency.preset_mismatch("Bambu Lab X1 Carbon", "Bambu X1C", xl))
        self.assertEqual(consistency.preset_mismatch("Prusa MK4S", "x", None), "")


class TestPreflightChecks(unittest.TestCase):
    def test_not_sliced_for_prusa(self):
        w = warnings("; filament_type = PLA\n; printer_model = Bambu Lab X1 Carbon\n", printer())
        self.assertTrue(any("not a Prusa printer" in x for x in w))

    def test_high_flow(self):
        hf = "; filament_type = PLA\n; printer_model = Prusa CORE One HF\n; printer_notes = PRINTER_MODEL_COREONE\\nHF_NOZZLE\n"
        self.assertTrue(gcode_meta.parse_text(hf).high_flow)
        self.assertTrue(any("sliced for a high-flow nozzle" in x for x in warnings(hf, printer("7.1.0"))))
        self.assertFalse(warnings(hf, printer("7.1.0", high_flow=True)))
        plain = "; filament_type = PLA\n; printer_model = Prusa CORE One\n"
        self.assertTrue(any("standard nozzle preset" in x for x in warnings(plain, printer("7.1.0", high_flow=True))))
        # The XL has no HF presets in Orca, so an HF nozzle there is not a slicing mistake.
        self.assertFalse(warnings("; filament_type = PLA\n; printer_model = Prusa XL 5T\n", printer(high_flow=True)))

    def test_abrasive(self):
        cf = "; filament_type = PA-CF\n; printer_model = Prusa XL 5T\n"
        t = printer()
        t.tools[0].material = "PA-CF"
        self.assertTrue(any("abrasive" in x for x in warnings(cf, t)))
        t.tools[0].hardened = True
        self.assertFalse(warnings(cf, t))
        hrc = "; filament_type = PLA\n; required_nozzle_HRC = 40\n"
        self.assertTrue(gcode_meta.parse_text(hrc).abrasive(0))
        self.assertFalse(gcode_meta.parse_text("; filament_type = PLA\n; required_nozzle_HRC = 0\n").abrasive(0))

    def test_reprint_uses_the_record(self):
        meta = gcode_meta.parse_text("; filament_type = PETG\n; nozzle_diameter = 0.4\n; printer_model = Prusa XL 5T\n")
        meta.used_tools = [0]
        again = gcode_meta.from_summary(gcode_meta.summary(meta))
        self.assertEqual(again.filament_types, ["PETG"])
        self.assertTrue(any("sliced for PETG, but PLA" in x for x in preflight.check_reprint(again, printer()).warnings))
        self.assertTrue(preflight.check_reprint(gcode_meta.GcodeMeta(), printer()).ok)  # nothing recorded


if __name__ == "__main__":
    unittest.main()
