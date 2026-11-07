"""The filament catalogue: merging Connect and the Open Filament Database, picking a base, the preset values."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prusa_orca.catalog import (
    SOURCE_CONNECT,
    SOURCE_OFD,
    SOURCE_ORCA,
    CatalogEntry,
    Nozzle,
    basic_color,
    brand_names,
    connect_entry,
    drop_imported,
    finishes,
    merge,
    misfit,
    ofd_entries,
    orca_entries,
    pick_base,
    preset_name,
    preset_values,
    recent_groups,
    remember,
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

    def test_same_product_merges_across_spellings(self):
        def c(name, typ, color):
            return CatalogEntry("Fiberlogy", name, typ, color=color, source=SOURCE_CONNECT, key=name)

        def o(name, typ, color):
            return CatalogEntry("Fiberlogy", name, typ, color=color, source=SOURCE_OFD, key=name, temps={"density": 1.27})

        connect = [
            c("Easy PETG Grey", "PETG", "#c5c5bf"),
            c("Easy PETG Onyx", "PETG", "#000000"),
            c("PETG Matte Black", "PETG", "#000000"),
        ]
        ofd = [
            o("Easy PET-G Gray", "PETG", "#bbbcbc"),
            o("Easy PET-G Onyx", "PETG", "#262626"),
            o("Easy PET-G Black", "PETG", "#000000"),
        ]
        merged = merge(connect, ofd)
        self.assertEqual([e.name for e in merged], ["Easy PETG Grey", "Easy PETG Onyx", "PETG Matte Black", "Easy PET-G Black"])
        self.assertEqual(merged[0].sources, [SOURCE_CONNECT, SOURCE_OFD])
        self.assertEqual(merged[0].temps, {"density": 1.27})
        self.assertEqual(merged[2].sources, [])  # "Matte" is another product than "Easy"

    def test_spelling_variants_merge(self):
        def pair(brand_c, name_c, type_c, brand_o, name_o, type_o, color="#000000", color_o=None):
            c = CatalogEntry(brand_c, name_c, type_c, color=color, source=SOURCE_CONNECT, key="c")
            o = CatalogEntry(brand_o, name_o, type_o, color=color_o or color, source=SOURCE_OFD, key="o")
            return len(merge([c], [o]))

        self.assertEqual(pair("BambuLab", "ABS Azure", "ABS", "Bambu Lab", "ABS Azure", "ABS"), 1)  # brand spacing
        self.assertEqual(pair("Extrudr", "DuraPro ABS black | RAL 9017", "ABS", "Extrudr", "DuraPro ABS Black", "ABS"), 1)
        self.assertEqual(pair("Prusament", "rPLA Corn Pigment", "PLA", "Prusament", "PLA r Corn Pigment", "PLA"), 1)
        self.assertEqual(pair("Prusament", "PETG Carbon Fiber Black", "PETGCF", "Prusament", "PETG CF Black", "PETG"), 1)
        self.assertEqual(
            pair("Polymaker", "ASA Army Brown", "ASA", "Polymaker", "Polylite ASA Army Brown", "ASA", "#624234", "#7e472a"), 1
        )
        self.assertEqual(pair("Fiberlogy", "Easy PLA Briliant Blue", "PLA", "Fiberlogy", "Easy PLA Brilliant Blue", "PLA"), 1)
        # A different product line is not the same filament, even with the same colour.
        self.assertEqual(pair("Prusament", "PLA Lightweight Galaxy Black", "PLA", "Prusament", "PLA Galaxy Black", "PLA"), 2)
        self.assertEqual(pair("Polymaker", "ASA Black", "ASA", "Polymaker", "PC Black", "PC"), 2)
        self.assertEqual(pair("Prusament", "PETG Jet Black", "PETG", "Prusament", "PETG Jet White", "PETG"), 2)

    def test_imported_filament_listed_once(self):
        orca = orca_entries([FilamentPreset("_local/prusa_plugin_filaments/eSUN PLA+ Red", vendor="eSUN", type="PLA")])
        self.assertEqual(orca[0].name, "eSUN PLA+ Red")
        db = CatalogEntry("eSUN", "PLA+ Red", "PLA", source=SOURCE_CONNECT, key="c")
        other = CatalogEntry("eSUN", "PLA+ Blue", "PLA", source=SOURCE_CONNECT, key="d")
        self.assertEqual(drop_imported([*orca, db, other], orca), [orca[0], other])

    def test_colours_and_filters(self):
        def e(brand, name, typ="PLA", color="", tags=()):
            return CatalogEntry(brand, name, typ, color=color, tags=list(tags))

        self.assertEqual(basic_color(e("X", "PLA Grey Green")), "green")  # the last colour word decides
        self.assertEqual(basic_color(e("X", "PLA Anthracite Grey")), "grey")
        self.assertEqual(basic_color(e("X", "PLA Rojo")), "red")
        self.assertEqual(basic_color(e("X", "PLA Galaxy", color="#1565c0")), "blue")  # no colour word: the code
        self.assertEqual(basic_color(e("X", "PLA Mystery", color="")), "")
        self.assertEqual(finishes(e("X", "Silk PLA Gold", tags=["translucent"])), ["silk", "translucent"])
        items = [
            e("Prusament", "PLA Galaxy Black", color="#3d3e3d"),
            e("eSUN 3D", "PLA+ Silk Red", color="#c00000"),
            e("eSUN", "PCTG Clear", "PCTG"),
            e("Fiberlogy", "PETG Blue", "PETG", color="#0050c0"),
        ]
        self.assertEqual([x.name for x in search(items, brand="eSUN")], ["PCTG Clear", "PLA+ Silk Red"])
        self.assertEqual([x.name for x in search(items, color="red")], ["PLA+ Silk Red"])
        self.assertEqual([x.name for x in search(items, finish="silk")], ["PLA+ Silk Red"])
        self.assertEqual([x.name for x in search(items, finish="transparent")], ["PCTG Clear"])
        self.assertEqual([x.name for x in search(items, color="red", finish="silk")], ["PLA+ Silk Red"])
        self.assertEqual([x.name for x in search(items, color="unknown")], ["PCTG Clear"])  # no word, no code
        self.assertEqual([x.name for x in search(items, finish="none")], ["PETG Blue"])  # "Galaxy" is glitter
        self.assertEqual([x.name for x in search(items, material="PETG")], ["PCTG Clear", "PETG Blue"])  # printer type
        self.assertEqual(brand_names(items), ["Prusament", "eSUN 3D", "Fiberlogy"])

    def test_nozzle_fit(self):
        cf = CatalogEntry("Prusament", "PETG Carbon Fiber Black", "PETGCF")
        hf = CatalogEntry("Polymaker", "Panchroma PLA", "PLA", tags=["high_flow"])
        plain = CatalogEntry("Prusament", "PLA Galaxy Black", "PLA")
        std = Nozzle(0.4)
        self.assertEqual(misfit(cf, std), "abrasive")
        self.assertEqual(misfit(cf, Nozzle(0.4, hardened=True)), "")
        self.assertEqual(misfit(hf, std), "high flow")
        self.assertEqual(misfit(plain, std), "")
        self.assertIn("0.6 mm", misfit(CatalogEntry("X", "Glitter PLA", "PLA", min_nozzle_diameter=0.6), std))

    def test_recent_list_and_orca_presets(self):
        a, b = CatalogEntry("A", "PLA", "PLA", key="a"), CatalogEntry("B", "PETG", "PETG", key="b")
        recent = remember(remember(remember([], a, 1), b, 2), a, 3)
        self.assertEqual([(e.key, e.tools) for e in recent], [("a", [3, 1]), ("b", [2])])
        groups = recent_groups(recent, 2)
        self.assertEqual([(g, e.key) for g, e in groups], [("Recent for T2", "b"), ("All recent", "a")])
        self.assertEqual([g for g, _ in recent_groups(recent, 0)], ["All recent", "All recent"])
        self.assertEqual(CatalogEntry.from_json(a.to_json()), a)
        self.assertIsNone(CatalogEntry.from_json({"name": "no brand"}))
        entries = orca_entries(PRESETS)
        self.assertEqual(len(entries), 3)  # the incompatible MINI preset is left out
        self.assertEqual(
            (entries[0].source, entries[0].name, entries[0].key), (SOURCE_ORCA, "Prusament PETG", "Prusament PETG @XL")
        )


if __name__ == "__main__":
    unittest.main()
