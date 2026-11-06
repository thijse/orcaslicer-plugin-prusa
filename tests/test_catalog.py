"""The filament catalogue: merging Connect and the Open Filament Database, picking a base, the preset values."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prusa_orca.catalog import (
    SOURCE_CONNECT,
    SOURCE_OFD,
    CatalogEntry,
    connect_entry,
    merge,
    ofd_entries,
    pick_base,
    preset_name,
    preset_values,
    search,
    sources_notice,
)
from prusa_orca.materials import FilamentPreset

CONNECT_NODE = {
    "material": {
        "uuid": "u-1",
        "name": "PLA+ Almond Yellow",
        "type": "PLA",
        "class": "FFF",
        "abbreviation": "PLA",
        "tags": ["industrially_compostable"],
        "brand": {"name": "eSUN"},
        "primaryColor": {"colorRgba": "#E6D690ff"},
        "properties": {"minPrintTemperature": 210, "maxPrintTemperature": 230, "minBedTemperature": None},
    }
}
OFD_DUMP = {
    "brands": [{"id": "b1", "name": "eSUN"}, {"id": "b2", "name": "SUNLU"}],
    "filaments": [
        {
            "id": "f1",
            "brand_id": "b1",
            "name": "PLA+",
            "material": "PLA",
            "density": 1.23,
            "min_bed_temperature": 45,
            "max_bed_temperature": 60,
        },
        {
            "id": "f2",
            "brand_id": "b2",
            "name": "PETG",
            "material": "PETG",
            "density": 1.27,
            "min_print_temperature": 230,
            "max_print_temperature": 250,
        },
        {"id": "f3", "brand_id": "b2", "name": "Old PLA", "material": "PLA", "discontinued": True},
    ],
    "variants": [
        {"id": "v1", "filament_id": "f1", "name": "Almond Yellow", "color_hex": "#e6d690"},
        {"id": "v2", "filament_id": "f2", "name": "Black", "color_hex": "#000000"},
        {"id": "v3", "filament_id": "f3", "name": "White", "color_hex": "#ffffff"},
    ],
}
PRESETS = [
    FilamentPreset("Prusament PETG @XL", type="PETG"),
    FilamentPreset("Generic PETG @Prusa XL", type="PETG"),
    FilamentPreset("Generic PLA @Prusa XL", type="PLA"),
    FilamentPreset("Generic PLA @Prusa MINI", type="PLA", compatible=False),
]


class TestCatalog(unittest.TestCase):
    def test_sources_in_one_shape(self):
        c = connect_entry(CONNECT_NODE)
        assert c is not None
        self.assertEqual((c.brand, c.type, c.color, c.connect_uuid), ("eSUN", "PLA", "#e6d690", "u-1"))
        self.assertEqual(c.temps, {"min_nozzle": 210, "max_nozzle": 230})
        ofd = ofd_entries(OFD_DUMP)
        self.assertEqual([e.name for e in ofd], ["PLA+ Almond Yellow", "PETG Black"])  # discontinued left out

    def test_connect_wins_and_ofd_fills_gaps(self):
        c = connect_entry(CONNECT_NODE)
        assert c is not None
        merged = merge([c], ofd_entries(OFD_DUMP))
        self.assertEqual(len(merged), 2)
        esun = merged[0]
        self.assertEqual(esun.source, SOURCE_CONNECT)
        self.assertEqual(esun.temps["min_nozzle"], 210)  # Connect's value kept
        self.assertEqual(esun.temps["density"], 1.23)  # gap filled from OFD
        self.assertEqual(esun.temps["max_bed"], 60)
        self.assertEqual(merged[1].source, SOURCE_OFD)

    def test_brand_aliases_merge_and_search_needs_every_word(self):
        c = CatalogEntry("eSUN", "PLA+ Red", "PLA Pro", source=SOURCE_CONNECT, key="c")  # Connect's product line
        o = CatalogEntry("eSUN 3D", "PLA+ Red", "PLA", source=SOURCE_OFD, key="o", temps={"density": 1.2})
        merged = merge([c], [o])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].temps, {"density": 1.2})
        petg = CatalogEntry("eSUN", "PETG Basic Black", "PETG")
        self.assertEqual(search([petg, c], "eSUN PLA+"), [c])

    def test_search_puts_prusament_first(self):
        entries = [CatalogEntry("eSUN", "PLA+ Red", "PLA"), CatalogEntry("Prusament", "PLA Galaxy Black", "PLA")]
        self.assertEqual([e.brand for e in search(entries, "pla")], ["Prusament", "eSUN"])
        self.assertEqual([e.brand for e in search(entries, "galaxy")], ["Prusament"])
        self.assertEqual(search(entries, "", material="PETG"), [])

    def test_base_prefers_prusament_then_generic_then_similar(self):
        base, _ = pick_base(CatalogEntry("Prusament", "PETG Jet Black", "PETG"), PRESETS)
        self.assertEqual(base.name if base else "", "Prusament PETG @XL")
        base, _ = pick_base(CatalogEntry("SUNLU", "PETG Black", "PETG"), PRESETS)
        self.assertEqual(base.name if base else "", "Generic PETG @Prusa XL")
        base, why = pick_base(CatalogEntry("Fiberlogy", "PCTG Clear", "PCTG"), PRESETS)
        self.assertEqual(base.name if base else "", "Generic PETG @Prusa XL")
        self.assertIn("closest", why)
        base, _ = pick_base(CatalogEntry("eSUN", "PLA+ Red", "PLA Pro"), PRESETS)
        self.assertEqual(base.name if base else "", "Generic PLA @Prusa XL")
        base, why = pick_base(CatalogEntry("X", "PEEK", "PEEK"), PRESETS)
        self.assertIsNone(base)
        self.assertIn("no PEEK profile", why)

    def test_preset_values_without_data_keep_the_base(self):
        base = PRESETS[2]
        entry = CatalogEntry("Bambu Lab", "PLA Basic Green", "PLA", color="#00ae42", source=SOURCE_CONNECT)
        values = preset_values(entry, base, preset_name(entry))
        self.assertEqual(values["inherits"], "Generic PLA @Prusa XL")
        self.assertEqual(values["default_filament_colour"], ["#00ae42"])
        self.assertNotIn("nozzle_temperature", values)
        self.assertIn("settings are those of the base", values["filament_notes"])

    def test_preset_values_use_the_middle_of_the_range(self):
        entry = CatalogEntry("eSUN", "PLA+", "PLA", temps={"min_nozzle": 210, "max_nozzle": 230, "min_bed": 45, "max_bed": 60})
        values = preset_values(entry, PRESETS[2], "eSUN PLA+")
        self.assertEqual(values["nozzle_temperature"], ["220"])
        self.assertEqual(values["hot_plate_temp"], ["50"])
        for key in ("type", "instantiation", "compatible_printers", "setting_id", "filament_id"):
            self.assertNotIn(key, values)  # those would make Orca treat it as a system preset

    def test_notice_when_a_source_is_missing(self):
        self.assertEqual(sources_notice("ok", "ok"), "")
        self.assertIn("Log in to Prusa Connect", sources_notice("login", "ok"))
        self.assertIn("Open Filament Database only", sources_notice("offline", "ok"))
        self.assertIn("Prusa Connect only", sources_notice("ok", "offline"))
        self.assertIn("3 days ago", sources_notice("ok", "cached", 3.2))
        self.assertEqual(sources_notice("ok", "cached", 0.5), "")
        self.assertIn("No filament database", sources_notice("offline", "offline"))


if __name__ == "__main__":
    unittest.main()
