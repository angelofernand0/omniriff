import socket
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.check import FAIL, PASS, WARN, check_audio, check_model, check_packages, check_port, check_ports, check_serial, format_rows  # noqa: E402

HOSTAPIS = [{"name": "MME"}, {"name": "Windows WASAPI"}, {"name": "ASIO"}]


def dev(name, api, ins, outs):
    return {"name": name, "hostapi": api, "max_input_channels": ins, "max_output_channels": outs}


def by_check(rows):
    return {r.check: r for r in rows}


class AudioCheckTests(unittest.TestCase):
    def test_solo_on_wasapi_passes(self):
        rows = by_check(check_audio([dev("Focusrite USB (Scarlett Solo USB)", 1, 2, 0),
                                     dev("Speakers (Focusrite USB)", 1, 0, 2)], HOSTAPIS, input_channel=2))
        self.assertEqual(rows["audio Focusrite device"].status, PASS)
        self.assertEqual(rows["audio input channel 2"].status, PASS)
        self.assertEqual(rows["audio stereo output"].status, PASS)
        self.assertEqual(rows["audio WASAPI"].status, PASS)
        self.assertEqual(rows["audio ASIO"].status, WARN)

    def test_missing_interface_fails_with_fix(self):
        rows = check_audio([dev("Realtek Microphone", 0, 2, 0)], HOSTAPIS, input_channel=2)
        self.assertEqual(rows[0].status, FAIL)
        self.assertIn("plug in the Solo", rows[0].fix)

    def test_single_channel_input_fails_for_input_two(self):
        rows = by_check(check_audio([dev("Scarlett Solo", 1, 1, 2)], HOSTAPIS, input_channel=2))
        self.assertEqual(rows["audio input channel 2"].status, FAIL)


class SerialCheckTests(unittest.TestCase):
    def test_recognizes_arduino_by_vendor_id(self):
        ports = [SimpleNamespace(device="COM4", description="USB Serial Device", vid=0x2341),
                 SimpleNamespace(device="COM1", description="Communications Port", vid=None)]
        row = check_serial(ports)[0]
        self.assertEqual(row.status, PASS)
        self.assertIn("--serial-port COM4", row.fix)

    def test_unknown_or_missing_ports_warn_not_fail(self):
        self.assertEqual(check_serial([SimpleNamespace(device="COM1", description="x", vid=None)])[0].status, WARN)
        self.assertEqual(check_serial([])[0].status, WARN)


class PortAndPackageTests(unittest.TestCase):
    def test_busy_port_is_reported(self):
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        holder.bind(("127.0.0.1", 0))
        port = holder.getsockname()[1]
        try:
            ok, detail = check_port("tcp", port)
            self.assertFalse(ok)
            self.assertIn("in use", detail)
        finally:
            holder.close()
        self.assertTrue(check_port("tcp", port)[0])

    def test_port_rows_use_probe(self):
        rows = check_ports({"state": ("tcp", 1), "controls": ("udp", 2)},
                           probe=lambda kind, port: (kind == "udp", "free" if kind == "udp" else "in use"))
        self.assertEqual([r.status for r in rows], [FAIL, PASS])

    def test_missing_required_package_fails_optional_warns(self):
        rows = by_check(check_packages(find_spec=lambda name: None))
        self.assertEqual(rows["package numpy"].status, FAIL)
        self.assertEqual(rows["package mediapipe (vision/)"].status, WARN)

    def test_summary_line(self):
        rows = check_ports({"state": ("tcp", 1)}, probe=lambda k, p: (True, "free"))
        self.assertIn("READY: 0 fail", format_rows(rows))


class ModelCheckTests(unittest.TestCase):
    def test_missing_model_warns_present_model_passes(self):
        import tempfile
        self.assertEqual(check_model("/nonexistent/hand_landmarker.task")[0].status, WARN)
        with tempfile.NamedTemporaryFile(suffix=".task") as f:
            self.assertEqual(check_model(f.name)[0].status, PASS)


if __name__ == "__main__":
    unittest.main()
