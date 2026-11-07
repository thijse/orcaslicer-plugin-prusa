"""Material type changes: which filaments count as another type, and a planned swap's progress."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prusa_orca.filament_sync import compare
from prusa_orca.material_swap import (
    SWAP_TIMEOUT,
    PlannedSwap,
    compatible_types,
    printer_type,
    swap_progress,
    type_change,
)
from prusa_orca.materials import FilamentPreset
from prusa_orca.model import ToolState


class TestMaterialSwap(unittest.TestCase):
    def test_printer_type(self):
        cases = {
            "PLA": "PLA",
            "PLA Pro": "PLA",
            "PLA+": "PLA",
            "PLA Silk": "PLA",
            "PETG": "PETG",
            "PETGCF": "PETG",
            "PETG-CF": "PETG",
            "PCTG": "PETG",
            "CPE": "PETG",
            "TPU": "FLEX",
            "PEBA": "FLEX",
            "PC Blend": "PC",
            "PC-ABS": "PC",
            "PA12": "PA",
            "PA6-CF": "PA",
            "PA-CF15": "PA",
            "ASA": "ASA",
            "PEEK": "PEEK",  # no printer preset: its own type
            "": "",
        }
        for material, expected in cases.items():
            self.assertEqual(printer_type(material), expected, material)

    def test_type_change(self):
        self.assertFalse(type_change("PLA", "PLA Pro"))  # brand or line only: no question
        self.assertFalse(type_change("PETG", "PETGCF"))
        self.assertTrue(type_change("PLA", "PETG"))
        self.assertFalse(type_change("PETG", "PCTG"))  # the printer loads PCTG as PETG
        self.assertTrue(type_change("ASA", "ABS"))
        self.assertTrue(type_change("PLA", "PEEK"))
        self.assertEqual(compatible_types("PETG")[:2], ["PETG", "CPE"])
        self.assertIn("PCTG", compatible_types("PETG"))
        self.assertEqual(compatible_types(""), [])
        self.assertFalse(type_change("", "PETG"))  # nothing loaded

    def test_swap_completes_when_the_printer_reports_the_type(self):
        swap = PlannedSwap(
            3, "PETG", "Polymaker", "PolyLite PETG Black", "#000000", "Polymaker PolyLite PETG Black", started=1000.0
        )
        self.assertEqual(swap_progress(swap, "PLA", True, now=1010.0), "waiting")
        self.assertEqual(swap_progress(swap, "", False, now=1020.0), "waiting")  # unloaded
        self.assertEqual(swap_progress(swap, "PETG", True, now=1030.0), "done")
        self.assertEqual(swap_progress(swap, "PLA", True, now=1000.0 + SWAP_TIMEOUT + 1), "expired")
        self.assertEqual(PlannedSwap.from_json(swap.to_json()), swap)
        self.assertIsNone(PlannedSwap.from_json({"tool_number": 1}))

    def test_sync_marks_another_type(self):
        tools = [ToolState(index=0, tool_number=1, material="PLA"), ToolState(index=1, tool_number=2, material="PLA")]
        presets = [FilamentPreset("Generic PLA @XL", type="PLA"), FilamentPreset("Generic PETG @XL", type="PETG")]
        rows = compare(tools, presets, ["Generic PLA @XL", "Generic PETG @XL"], [])
        self.assertEqual([r["type_differs"] for r in rows], [False, True])
        self.assertEqual(rows[1]["slot_type"], "PETG")


if __name__ == "__main__":
    unittest.main()
