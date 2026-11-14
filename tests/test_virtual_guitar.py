"""Hardware-free virtual guitar tests."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from tools.virtual_guitar.render import (
    load_control_script,
    render_virtual_guitar,
    synthetic_signal,
)

ROOT = Path(__file__).resolve().parents[1]
SR = 16000


class VirtualGuitarTests(unittest.TestCase):
    def test_synthetic_render_is_deterministic_finite_and_labeled(self):
        signal = synthetic_signal(0.5, SR, seed=11)
        a, report_a = render_virtual_guitar(signal, SR, tail_seconds=0.1, blocksize=128)
        b, report_b = render_virtual_guitar(signal, SR, tail_seconds=0.1, blocksize=128)
        np.testing.assert_array_equal(a, b)
        self.assertTrue(np.all(np.isfinite(a)))
        self.assertEqual(report_a["label"], "SIMULATED VIRTUAL GUITAR")
        self.assertFalse(report_a["hardware_latency_measured"])
        self.assertEqual(report_a["engine"]["clipped_samples"], 0)
        self.assertEqual(report_a["output"], report_b["output"])

    def test_dark_filter_reduces_high_frequency_energy(self):
        signal = synthetic_signal(1.0, SR, seed=4)
        open_audio, open_report = render_virtual_guitar(signal, SR, tail_seconds=0, filter_value=1.0)
        dark_audio, dark_report = render_virtual_guitar(signal, SR, tail_seconds=0, filter_value=0.0)
        self.assertGreater(open_report["output"]["high_band_energy_pct"],
                           dark_report["output"]["high_band_energy_pct"] * 10)
        self.assertGreater(float(np.sqrt(np.mean(open_audio[:, 0] ** 2))),
                           float(np.sqrt(np.mean(dark_audio[:, 0] ** 2))))

    def test_validated_demo_controls_drive_real_engine(self):
        controls = load_control_script(ROOT / "engine" / "demo-controls.jsonl")
        signal = synthetic_signal(7.1, SR, seed=2)
        _, report = render_virtual_guitar(signal, SR, controls=controls, tail_seconds=0, blocksize=128)
        self.assertEqual(report["control_events_applied"], 8)
        self.assertEqual(report["engine"]["events"]["accepted"], 10)  # two initial values + script
        self.assertEqual(report["engine"]["loop"]["state"], "idle")
        self.assertEqual(report["engine"]["filter"]["target"], 0.8)
        self.assertEqual(report["engine"]["reverb"]["target"], 0.0)

    def test_rejects_nonfinite_input(self):
        with self.assertRaises(ValueError):
            render_virtual_guitar(np.array([0.0, np.nan], np.float32), SR)


if __name__ == "__main__":
    unittest.main()
