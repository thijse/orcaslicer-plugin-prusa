"""Offline tests for prusa_orca, using sanitized responses captured from a Prusa XL."""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
sys.path.insert(0, ROOT)

from prusa_orca.backends.aggregate import merge
from prusa_orca.backends.connect import build_authorize_url, code_from_redirect, generate_pkce_pair, parse_graphql_tools
from prusa_orca.backends.prusalink import extract_plate_gcode, parse_status, printer_file_name
from prusa_orca.dialect import (
    build_ams_units,
    build_get_version,
    build_push_status,
    map_ams_to_prusa_tool_mapping,
    tool_mapping_problem,
)
from prusa_orca.materials import FilamentIdResolver, FilamentPreset, match_preset, pick_connect_material, tray_info_idx
from prusa_orca.model import InterpretedPhase, JobState, PrinterTelemetry, RawPrinterState, ToolState
from prusa_orca.phase import interpret_phase
from prusa_orca.settings import Settings, orca_data_dir


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


class TestConnectTools(unittest.TestCase):
    def setUp(self):
        self.tools = parse_graphql_tools(fixture("graphql_fff_telemetry.json"))

    def test_five_tools_in_order(self):
        self.assertEqual([t.tool_number for t in self.tools], [1, 2, 3, 4, 5])

    def test_named_material_with_colour(self):
        t1 = self.tools[0]
        self.assertTrue(t1.is_loaded)
        self.assertEqual((t1.vendor, t1.name, t1.material, t1.color), ("Prusament", "PLA Army Green", "PLA", "#524F2F"))

    def test_type_only_material_has_no_colour(self):
        t2, t5 = self.tools[1], self.tools[4]
        self.assertEqual((t2.material, t2.name, t2.color), ("PLA", "", ""))
        self.assertEqual(t5.material, "PETG")
        self.assertEqual(t5.nozzle_diameter, 0.6)


class TestPrusaLink(unittest.TestCase):
    def test_idle_status(self):
        t = parse_status(fixture("lan_status_idle.json"), "192.0.2.10")
        self.assertEqual(t.raw_state, RawPrinterState.IDLE)
        self.assertEqual(t.interpreted_phase, InterpretedPhase.IDLE)
        self.assertAlmostEqual(t.bed_temperature, 20.6)
        self.assertEqual(t.tools, [])


class TestMerge(unittest.TestCase):
    def test_lan_values_and_cloud_tools(self):
        lan = parse_status(fixture("lan_status_idle.json"))
        cloud = PrinterTelemetry(
            connected=True,
            model="Original Prusa XL",
            firmware_version="8.0.1",
            tools=parse_graphql_tools(fixture("graphql_fff_telemetry.json")),
            bed_temperature=99.0,
        )
        merged = merge(lan, cloud)
        assert merged is not None
        self.assertEqual(len(merged.tools), 5)
        self.assertAlmostEqual(merged.bed_temperature, 20.6)
        self.assertEqual(merged.source, "lan+connect")

    def test_ready_comes_from_connect(self):
        lan = parse_status(fixture("lan_status_idle.json"))
        self.assertEqual(lan.raw_state, RawPrinterState.IDLE)
        merged = merge(lan, PrinterTelemetry(connected=True, raw_state=RawPrinterState.READY))
        assert merged is not None
        self.assertEqual(merged.raw_state, RawPrinterState.READY)

    def test_either_side_missing(self):
        lan = parse_status(fixture("lan_status_idle.json"))
        self.assertIs(merge(lan, None), lan)
        self.assertIsNone(merge(None, None))


class TestDialect(unittest.TestCase):
    def setUp(self):
        self.tools = parse_graphql_tools(fixture("graphql_fff_telemetry.json"))

    def test_ams_layout_for_five_tools(self):
        ams = build_ams_units(self.tools)
        self.assertEqual(len(ams["ams"]), 2)
        self.assertEqual(ams["tray_exist_bits"], "1F")
        self.assertEqual(ams["ams"][0]["tray"][0]["tray_color"], "524F2FFF")
        self.assertEqual(ams["ams"][1]["tray"][0]["tray_type"], "PETG")
        self.assertEqual(len(ams["ams"][1]["tray"]), 1)

    def test_unknown_colour_is_grey_and_empty_tool_is_placeholder(self):
        tools = [
            ToolState(index=0, tool_number=1, material="PLA", color="", is_loaded=True),
            ToolState(index=1, tool_number=2, material="", is_loaded=False),
        ]
        trays = build_ams_units(tools)["ams"][0]["tray"]
        self.assertEqual(trays[0]["tray_color"], "9E9E9EFF")
        self.assertEqual(trays[1].get("tray_slot_placeholder"), "1")

    def test_push_status(self):
        t = PrinterTelemetry(
            connected=True,
            raw_state=RawPrinterState.PRINTING,
            nozzle_temperature=215.0,
            tools=self.tools,
            job=JobState(progress_percent=42.0, time_remaining_seconds=1200),
        )
        p = build_push_status(t, 7, lambda tool: "OGFL99")["print"]
        self.assertEqual(
            (p["command"], p["gcode_state"], p["mc_percent"], p["mc_remaining_time"]), ("push_status", "RUNNING", 42, 20)
        )
        self.assertEqual(p["ams"]["ams"][0]["tray"][0]["tray_info_idx"], "OGFL99")

    def test_version(self):
        v = build_get_version(PrinterTelemetry(firmware_version="8.0.1+17071"), 3)
        self.assertEqual(v["info"]["module"][0]["name"], "ota")

    def test_tool_mapping(self):
        self.assertEqual(map_ams_to_prusa_tool_mapping("0:2,1:0", 2), {"1": [3], "2": [1]})


class TestMaterials(unittest.TestCase):
    PRESETS = (
        FilamentPreset("Generic PLA @Prusa XL", "GFL99", "Generic", "PLA"),
        FilamentPreset("Prusament PLA @Prusa XL", "PFL01", "Prusament", "PLA"),
        FilamentPreset("Prusament PLA Army Green @Prusa XL", "PFL07", "Prusament", "PLA"),
        FilamentPreset("Generic PETG @Prusa XL", "GFG99", "Generic", "PETG"),
        FilamentPreset("Generic PETG @Other", "GFG98", "Generic", "PETG", compatible=False),
    )

    def tool(self, **kw):
        return ToolState(index=0, tool_number=1, is_loaded=True, **kw)

    def match(self, tool):
        preset = match_preset(tool, self.PRESETS)
        assert preset is not None
        return preset

    def test_named_spool_matches_exact_preset(self):
        t = self.tool(material="PLA", vendor="Prusament", name="PLA Army Green")
        self.assertEqual(self.match(t).filament_id, "PFL07")

    def test_type_only_prefers_generic(self):
        self.assertEqual(self.match(self.tool(material="PLA")).filament_id, "GFL99")
        self.assertEqual(self.match(self.tool(material="PETG")).filament_id, "GFG99")

    def test_unknown_type_and_fallback_id(self):
        t = self.tool(material="ASA")
        self.assertIsNone(match_preset(t, self.PRESETS))
        self.assertEqual(tray_info_idx(t, None), "PRUSA-ASA")


class TestPrintJob(unittest.TestCase):
    def test_extracts_the_requested_plate(self):
        import zipfile

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "job.gcode.3mf")
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("Metadata/plate_1.gcode", "G1 X1\n")
                z.writestr("Metadata/plate_2.gcode", "G1 X2\n")
                z.writestr("Metadata/plate_2.gcode.md5", "x")
            with open(extract_plate_gcode(path, 2, d), encoding="utf-8") as f:
                self.assertEqual(f.read(), "G1 X2\n")
            with self.assertRaises(ValueError):
                extract_plate_gcode(path, 3, d)

    def test_file_name_is_safe(self):
        self.assertEqual(printer_file_name("My part (v2).gcode.3mf", 1), "My_part_v2.gcode")
        self.assertEqual(printer_file_name("Box", 3), "Box_plate3.gcode")

    def test_tool_mapping(self):
        self.assertEqual(tool_mapping_problem("[0, 1, -1, 3]"), "")
        self.assertIn("tool 3", tool_mapping_problem("[2, 1]"))
        self.assertEqual(tool_mapping_problem(""), "")


class TestPickConnectMaterial(unittest.TestCase):
    NODES = (
        {
            "uuid": "a",
            "material": {
                "name": "PLA Lightweight Army Green",
                "abbreviation": "PLA",
                "brand": {"name": "Prusament"},
                "primaryColor": {"colorRgba": "#524f2fff"},
            },
        },
        {
            "uuid": "b",
            "material": {
                "name": "PLA Army Green",
                "abbreviation": "PLA",
                "brand": {"name": "Prusament"},
                "primaryColor": {"colorRgba": "#524f2fff"},
            },
        },
        {"uuid": "c", "material": {"name": "PLA Army Green", "abbreviation": "PLA", "brand": {"name": "FormFutura"}}},
        {"uuid": "d", "material": {"name": "PETG Army Green", "abbreviation": "PETG", "brand": {"name": "Prusament"}}},
    )

    def test_prefers_type_vendor_and_fewest_extra_words(self):
        pick = pick_connect_material(list(self.NODES), "Prusament", "Prusament PLA Army Green", "PLA", "#524F2F")
        assert pick is not None
        self.assertEqual(pick["uuid"], "b")

    def test_wrong_type_never_matches(self):
        self.assertIsNone(pick_connect_material(list(self.NODES[3:]), "Prusament", "Army Green", "PLA"))


class TestFilamentIdResolver(unittest.TestCase):
    def test_follows_system_and_user_inherits(self):
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.join(d, "system", "Prusa", "filament")
            os.makedirs(folder)
            files = {
                "Prusament PLA @base": {"filament_id": "OFnO4wnf"},
                "Prusament PLA @XL": {"inherits": "Prusament PLA @base"},
            }
            for name, data in files.items():
                with open(os.path.join(folder, name + ".json"), "w", encoding="utf-8") as f:
                    json.dump(data, f)
            user = os.path.join(d, "user.json")
            with open(user, "w", encoding="utf-8") as f:
                json.dump({"inherits": "Prusament PLA @XL"}, f)
            resolver = FilamentIdResolver(os.path.join(d, "system"))
            self.assertEqual(resolver.resolve(os.path.join(folder, "Prusament PLA @XL.json")), "OFnO4wnf")
            self.assertEqual(resolver.resolve(user), "OFnO4wnf")
            self.assertEqual(resolver.resolve(os.path.join(d, "missing.json")), "")


class TestPhase(unittest.TestCase):
    def test_attention_split(self):
        mid = PrinterTelemetry(connected=True, raw_state=RawPrinterState.ATTENTION, job=JobState(progress_percent=55.0))
        self.assertEqual(interpret_phase(mid), InterpretedPhase.ATTENTION_MID_PRINT)
        cold = PrinterTelemetry(connected=True, raw_state=RawPrinterState.ATTENTION)
        self.assertEqual(interpret_phase(cold), InterpretedPhase.ATTENTION_BEFORE_HEATING)


class TestAuthHelpers(unittest.TestCase):
    def test_authorize_url_uses_prusaslicer_client(self):
        _, challenge = generate_pkce_pair()
        url = build_authorize_url(challenge)
        self.assertIn("client_id=oamhmhZez7opFosnwzElIgE2oGgI2iJORSkw587O", url)
        self.assertIn("scope=basic_info", url)

    def test_code_from_redirect(self):
        self.assertEqual(code_from_redirect("prusaslicer://login?code=Ab12Cd&state=x"), "Ab12Cd")
        self.assertEqual(code_from_redirect("  Ab12Cd \n"), "Ab12Cd")


class TestSettings(unittest.TestCase):
    def test_fill_from_connect_only_fills_empty_fields(self):
        with tempfile.TemporaryDirectory() as d:
            s = Settings(d)
            s.update({"prusalink": {"password": "mine"}})
            filled = s.fill_from_connect(fixture("connect_printer.json"))
            self.assertEqual(s.values["prusalink"]["host"], "192.0.2.10")
            self.assertEqual(s.values["prusalink"]["password"], "mine")
            self.assertEqual(s.values["prusalink"]["api_key"], "")
            self.assertEqual(s.values["connect"]["api_key"], "CONNECTKEY")
            self.assertIn("PrusaLink host", filled)
            self.assertEqual(Settings(d).values["prusalink"]["host"], "192.0.2.10")

    def test_public_view_hides_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            s = Settings(d)
            s.update({"prusalink": {"password": "secret"}})
            self.assertIs(s.public_view()["prusalink"]["password"], True)
            self.assertEqual(s.lan_secret, "secret")

    def test_orca_data_dir_for_local_and_cloud_storage(self):
        data = os.path.join("base", "OrcaSlicer")
        local = os.path.join(data, "orca_plugins", "plugin_data", "prusa_plugin")
        cloud = os.path.join(data, "orca_plugins", "plugin_data", "_subscribed", "user1", "uuid1")
        self.assertEqual(orca_data_dir(local), data)
        self.assertEqual(orca_data_dir(cloud), data)


class TestControl(unittest.TestCase):
    def test_orca_device_gcode_maps_to_connect_commands(self):
        from prusa_orca.control import gcode_to_commands

        self.assertEqual(gcode_to_commands("M104 S215\n"), [("SET_NOZZLE_TEMPERATURE", {"nozzle_temperature": 215})])
        self.assertEqual(gcode_to_commands("M140 S500\n"), [("SET_HEATBED_TEMPERATURE", {"bed_temperature": 120})])
        self.assertEqual(gcode_to_commands("G28 \n"), [("HOME", {"axis": "XYZ"})])
        self.assertEqual(gcode_to_commands("G28 X\n"), [("HOME", {"axis": "X"})])
        self.assertEqual(gcode_to_commands("G91 \nG1 X10.0 F3000\nG90 \n"), [("MOVE", {"feedrate": 3000, "x": 10.0})])
        self.assertEqual(gcode_to_commands("G91 \nG1 Z-1.0 F900\nG90 \n"), [("MOVE_Z", {"feedrate": 600, "distance": -1.0})])
        self.assertEqual(gcode_to_commands("G1 X10\nM106 P1 S255\n"), [])

    def test_ready_action_follows_supported_states(self):
        from prusa_orca.control import ready_action

        supported = {"SET_PRINTER_READY": ["STOPPED", "IDLE", "FINISHED", "READY"], "CANCEL_PRINTER_READY": ["READY"]}
        self.assertEqual(ready_action(supported, "IDLE"), {"name": "SET_PRINTER_READY", "label": "Set ready"})
        self.assertEqual(ready_action(supported, "READY"), {"name": "CANCEL_PRINTER_READY", "label": "Cancel ready"})
        self.assertIsNone(ready_action(supported, "PRINTING"))
        self.assertIsNone(ready_action({}, "IDLE"))

    def test_camera_hint_explains_a_stale_or_missing_picture(self):
        from prusa_orca.control import camera_hint

        self.assertEqual(camera_hint(True, 20, "", True), "")
        self.assertIn("3 min", camera_hint(True, 180, "", True))
        self.assertIn("Log in", camera_hint(False, None, "", False))
        self.assertIn("Restart OrcaSlicer", camera_hint(False, None, 'audited operation "socket.bind" without permission', True))
        self.assertEqual(camera_hint(False, None, "", True), "")

    def test_push_status_reports_homed_axes_and_temperature_limits(self):
        p = build_push_status(PrinterTelemetry(connected=True), 1)["print"]
        self.assertEqual(p["home_flag"] & 0b111, 0b111)
        self.assertEqual(p["nozzle_temp_range"], [0, 290])


class TestPresetSync(unittest.TestCase):
    def setUp(self):
        from prusa_orca.model import ToolState

        self.tools = [ToolState(index=i, tool_number=i + 1) for i in range(5)]
        self.tools[4].nozzle_diameter, self.tools[4].hardened = 0.6, True

    def test_matching_preset_needs_nothing(self):
        from prusa_orca.preset_sync import compare, preset_to_printer, printer_to_preset

        d, t = "0.4,0.4,0.4,0.4,0.6", "brass,brass,brass,brass,hardened_steel"
        rows = compare(self.tools, d, t)
        self.assertEqual(printer_to_preset(rows, d, t), {})
        self.assertEqual(preset_to_printer(rows), [])

    def test_both_directions(self):
        from prusa_orca.preset_sync import compare, preset_to_printer, printer_to_preset

        d, t = "0.4,0.4,0.4,0.4,0.4", ["stainless_steel"] * 4 + ["brass"]
        rows = compare(self.tools, d, t)
        self.assertEqual(
            printer_to_preset(rows, d, t),
            {
                "nozzle_diameter": "0.4,0.4,0.4,0.4,0.6",
                "nozzle_type": "stainless_steel,stainless_steel,stainless_steel,stainless_steel,hardened_steel",
            },
        )
        self.assertEqual(
            preset_to_printer(rows),
            [
                ("SET_TOOL_NOZZLE_DIAMETER", {"tool_number": 5, "nozzle_diameter": 0.4}),
                ("SET_TOOL_HARDENED", {"tool_number": 5, "hardened": False}),
            ],
        )

    def test_unknown_nozzle_type_is_not_a_difference(self):
        from prusa_orca.preset_sync import compare

        rows = compare(self.tools, "0.4,0.4,0.4,0.4,0.6", "")
        self.assertFalse(any(r["hardened_differs"] for r in rows))


class TestFilamentSync(unittest.TestCase):
    def test_compare_and_colours(self):
        from prusa_orca.filament_sync import colours_from_printer, compare, parse_colours
        from prusa_orca.materials import FilamentPreset
        from prusa_orca.model import ToolState

        tools = [
            ToolState(index=0, tool_number=1, material="PLA", vendor="Prusament", name="PLA Army Green", color="#4b5320"),
            ToolState(index=1, tool_number=2, material="", is_loaded=False),
        ]
        presets = [
            FilamentPreset("Prusament PLA @XL 5T", vendor="Prusament", type="PLA"),
            FilamentPreset("Generic PLA @XL 5T", vendor="Generic", type="PLA"),
        ]
        colours = parse_colours('"#FFFFFF";"#00AE42"')
        rows = compare(tools, presets, ["Generic PLA @XL 5T", "Generic PETG @XL 5T"], colours)
        self.assertEqual(rows[0]["match"], "Prusament PLA @XL 5T")
        self.assertTrue(rows[0]["preset_differs"] and rows[0]["color_differs"])
        self.assertFalse(rows[1]["preset_differs"] or rows[1]["color_differs"])
        self.assertEqual(colours_from_printer(rows, colours), ["#4B5320", "#00AE42"])

    def test_bare_material_type_keeps_a_specific_preset(self):
        from prusa_orca.filament_sync import compare
        from prusa_orca.materials import FilamentPreset
        from prusa_orca.model import ToolState

        tools = [ToolState(index=0, tool_number=1, material="PLA", color="")]
        presets = [
            FilamentPreset("Generic PLA", type="PLA"),
            FilamentPreset("Polymaker PolyTerra PLA", vendor="Polymaker", type="PLA"),
        ]
        row = compare(tools, presets, ["Polymaker PolyTerra PLA"], ["#FFFFFF"])[0]
        self.assertFalse(row["preset_differs"] or row["color_differs"])


class TestPagesHtml(unittest.TestCase):
    def test_placeholders_are_filled(self):
        from prusa_orca.ui.page_html import PAGES_HTML

        self.assertNotIn("__PRINTER_SVG__", PAGES_HTML)
        self.assertIn('src="data:image/webp;base64,', PAGES_HTML)


class TestAggregateTools(unittest.TestCase):
    def test_keeps_last_tools_when_connect_omits_them(self):
        from prusa_orca.backends.aggregate import AggregateBackend
        from prusa_orca.backends.connect import ConnectBackend, TokenStore

        answers = [
            PrinterTelemetry(connected=True, tools=[ToolState(index=0, tool_number=1, material="PLA")]),
            PrinterTelemetry(connected=True, tools=[]),
        ]

        class FakeCloud(ConnectBackend):
            def __init__(self):
                super().__init__(TokenStore(os.devnull), "")

            def fetch_telemetry(self):
                return answers.pop(0)

        backend = AggregateBackend(None, FakeCloud(), tools_interval=0)
        backend.fetch_status()
        snapshot = backend.fetch_status()
        assert snapshot is not None
        self.assertEqual([t.material for t in snapshot.tools], ["PLA"])


class TestJobDetail(unittest.TestCase):
    def test_layers_from_heights_and_job_name_reach_push_status(self):
        lan = PrinterTelemetry(
            connected=True,
            raw_state=RawPrinterState.PRINTING,
            axis_z=5.0,
            job=JobState(job_id=462, file_name="ORCA_P~1.GCO", display_name="cube.gcode", progress_percent=6.0),
        )
        cloud = PrinterTelemetry(
            connected=True, raw_state=RawPrinterState.PRINTING, job=JobState(job_id=447, total_height=36.05, layer_height=0.15)
        )
        before = PrinterTelemetry(connected=True, job=JobState(job_id=462, layer_num=32))
        merged = merge(lan, cloud, before)
        assert merged is not None
        p = build_push_status(merged, 1)["print"]
        self.assertEqual((p["layer_num"], p["total_layer_num"]), (33, 240))
        self.assertEqual((p["gcode_file"], p["subtask_name"]), ("ORCA_P~1.GCO", "cube.gcode"))

    def test_layer_sequence_from_a_real_print(self):
        # Z heights logged on the XL: probing, first layers, a pause (head lifted to 40 mm), resume.
        layers, last = [], 0
        for z in (4.9, 14.5, 11.1, 0.2, 0.3, 0.6, 40.0, 0.6, 1.1):
            job = JobState(total_height=36.05, layer_height=0.15)
            job.estimate_layers(z, last)
            last = job.layer_num
            layers.append(last)
        self.assertEqual(layers, [0, 0, 0, 1, 2, 4, 4, 4, 7])

    def test_layer_when_joining_a_print_under_way(self):
        job = JobState(total_height=36.05, layer_height=0.15, progress_percent=31.0)
        job.estimate_layers(10.5)
        self.assertEqual(job.layer_num, 70)

    def test_layer_kept_when_head_parked_above_model(self):
        job = JobState(total_height=36.05, layer_height=0.15)
        job.estimate_layers(40.1, 56)
        self.assertEqual((job.layer_num, job.total_layer_num), (56, 240))

    def test_no_layers_without_layer_height(self):
        job = JobState(total_height=36.05)
        job.estimate_layers(5.0)
        self.assertEqual(job.total_layer_num, 0)
        self.assertNotIn("layer_num", build_push_status(PrinterTelemetry(connected=True, job=job), 1)["print"])


if __name__ == "__main__":
    unittest.main()
