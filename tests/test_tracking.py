import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prusa_orca import gcode_meta, preflight
from prusa_orca.history import PrintHistory, PrintTracker, new_record
from prusa_orca.model import JobState, PrinterTelemetry, RawPrinterState, ToolState

GCODE = """; HEADER_BLOCK_START
; model printing time: 1h 2m 3s; total estimated time: 1h 10m 0s
; HEADER_BLOCK_END
T0
G1 X1
T2 ; change
; filament used [g] = 10.5, 0, 3.25
; CONFIG_BLOCK_START
; filament_type = PLA;PETG;PLA
; filament_settings_id = "Prusament PLA";"Generic PETG";"Generic PLA"
; nozzle_diameter = 0.4,0.4,0.6
; CONFIG_BLOCK_END
"""


def tools(*materials):
    return [ToolState(index=i, tool_number=i + 1, material=m, is_loaded=bool(m)) for i, m in enumerate(materials)]


class TestGcodeMeta(unittest.TestCase):
    def test_read(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "a.gcode")
            with open(path, "w") as f:
                f.write(GCODE)
            meta = gcode_meta.read(path)
        self.assertEqual(meta.filament_types, ["PLA", "PETG", "PLA"])
        self.assertEqual(meta.filament_presets[0], "Prusament PLA")
        self.assertEqual(meta.used_tools, [0, 2])
        self.assertEqual(meta.estimated_seconds, 4200)
        self.assertEqual(meta.filament_used_g, [10.5, 0.0, 3.25])
        self.assertEqual(meta.nozzle_diameters, [0.4, 0.4, 0.6])


class TestPreflight(unittest.TestCase):
    def setUp(self):
        self.meta = gcode_meta.parse_text(GCODE)
        self.meta.used_tools = [0, 2]

    def test_matching_tools_pass(self):
        t = PrinterTelemetry(connected=True, raw_state=RawPrinterState.IDLE, tools=tools("PLA", "PLA", "PLA"))
        t.tools[2].nozzle_diameter = 0.6
        self.assertTrue(preflight.check(self.meta, t, True).ok)  # T2 (PETG) isn't used

    def test_wrong_material_nozzle_and_busy(self):
        t = PrinterTelemetry(connected=True, raw_state=RawPrinterState.PRINTING, tools=tools("PETG", "PLA", ""))
        r = preflight.check(self.meta, t, True)
        self.assertEqual(len(r.problems), 1)
        self.assertTrue(any("T1: sliced for PLA, but PETG" in w for w in r.warnings))
        self.assertTrue(any("T3: sliced for PLA, but the printer reports no filament" in w for w in r.warnings))
        self.assertTrue(any("0.6 mm nozzle" in w for w in r.warnings))
        self.assertFalse(preflight.check(self.meta, t, False).problems)  # upload only: busy is fine


def poll(state, job_id=None, progress=0.0, layer=0, left=0, name="cube.gcode"):
    job = JobState(
        job_id=job_id,
        file_name=name if job_id else "",
        display_name=name if job_id else "",
        progress_percent=progress,
        layer_num=layer,
        total_layer_num=100,
        time_remaining_seconds=left,
    )
    return PrinterTelemetry(connected=True, raw_state=state, job=job)


class TestTracker(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.history = PrintHistory(os.path.join(self.dir.name, "history.json"))
        self.tracker = PrintTracker(self.history)

    def tearDown(self):
        self.dir.cleanup()

    def events(self, t):
        return [e for e, _ in self.tracker.update(t)]

    def test_full_print(self):
        record = new_record("cube.gcode", "cube", 1, "", {}, {}, True, [])
        self.tracker.handover(record)
        self.assertEqual(self.events(poll(RawPrinterState.IDLE)), [])
        self.assertEqual(self.events(poll(RawPrinterState.PRINTING, 7, 1)), ["started"])
        self.assertEqual(self.events(poll(RawPrinterState.PRINTING, 7, 5, layer=2)), ["first_layer"])
        self.assertEqual(self.events(poll(RawPrinterState.PAUSED, 7, 20, layer=10)), ["paused"])
        self.assertEqual(self.events(poll(RawPrinterState.PRINTING, 7, 90, layer=90, left=300)), ["near_end"])
        self.assertEqual(self.events(poll(RawPrinterState.PRINTING, 7, 99, layer=100)), [])
        self.assertEqual(self.events(poll(RawPrinterState.FINISHED)), ["finished"])
        self.assertEqual(record["result"], "finished")
        self.assertEqual(record["job_id"], 7)
        # Persisted and reloaded.
        self.assertEqual(PrintHistory(self.history.path).records[0]["result"], "finished")

    def test_stop_and_foreign_job(self):
        self.assertEqual(self.events(poll(RawPrinterState.PRINTING, 8, 10, name="other.gcode")), ["started"])
        self.assertEqual(self.history.records[0]["source"], "printer")
        self.assertEqual(self.events(poll(RawPrinterState.STOPPED)), ["stopped"])

    def test_resume_after_restart(self):
        self.tracker.update(poll(RawPrinterState.PRINTING, 9, 10))
        tracker = PrintTracker(PrintHistory(self.history.path))
        self.assertEqual([e for e, _ in tracker.update(poll(RawPrinterState.PRINTING, 9, 40, layer=40))], [])
        self.assertEqual(len(tracker.history.records), 1)

    def test_stale_open_record_closes(self):
        self.tracker.update(poll(RawPrinterState.PRINTING, 9, 10))
        tracker = PrintTracker(PrintHistory(self.history.path))
        tracker.update(poll(RawPrinterState.IDLE))
        self.assertEqual(tracker.history.records[0]["result"], "unknown")


if __name__ == "__main__":
    unittest.main()
