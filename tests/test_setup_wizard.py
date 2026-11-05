import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prusa_orca.setup_wizard import propose

DETAIL = {"uuid": "u-1", "name": "Prusa XL", "printer_type": "3.1.0", "prusalink_api_key": "KEY",
          "network_info": {"lan_ipv4": "192.168.1.50", "hostname": "prusa-xl"}}
CAMERA = {"name": "Buddy3D Camera", "features": ["GetSnapshot", "RtspStream"],
          "config": {"network_info": {"wifi_ipv4": "192.168.1.60"}}}


class TestPropose(unittest.TestCase):
    def test_everything_from_connect(self):
        p = propose(DETAIL, [CAMERA])
        self.assertEqual(p.patch["prusalink"], {"host": "192.168.1.50", "api_key": "KEY", "password": ""})
        self.assertEqual(p.patch["connect"]["printer_uuid"], "u-1")
        self.assertEqual(p.patch["camera"]["rtsp_url"], "rtsp://192.168.1.60/live")
        self.assertEqual(p.missing, [])
        self.assertIn("Printer: Prusa XL", p.found)
        self.assertTrue(p.notes)
        self.assertIn("Printer: Desk (Prusa MK4S)", propose({"name": "Desk", "printer_type": "1.4.1"}, []).found)

    def test_missing_values_explain_where_to_find_them(self):
        p = propose({"uuid": "u-2", "printer_type": "1.4.1"}, [])
        self.assertNotIn("host", p.patch["prusalink"])
        self.assertTrue(any("Settings > Network" in m for m in p.missing))
        self.assertTrue(any("PrusaLink password" in m for m in p.missing))
        self.assertNotIn("rtsp_url", p.patch["camera"])

    def test_camera_without_rtsp_uses_snapshots(self):
        cam = {**CAMERA, "features": ["GetSnapshot"]}
        p = propose(DETAIL, [cam])
        self.assertNotIn("rtsp_url", p.patch["camera"])
        self.assertIn("Camera: snapshots through Prusa Connect", p.found)


if __name__ == "__main__":
    unittest.main()
