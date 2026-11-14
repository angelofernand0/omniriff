"""Tests for Gesture Rhythmic LFO (vision/lfo.py)."""
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from vision.lfo import GestureLFO, LFOConfig, LFOWaveform


class GestureLFOTests(unittest.TestCase):
    def setUp(self):
        schema_path = Path(__file__).resolve().parents[1] / 'protocol/control.schema.json'
        self.schema = json.loads(schema_path.read_text())
        self.validator = Draft202012Validator(self.schema)

    def test_subdivisions_from_height(self):
        lfo = GestureLFO(LFOConfig(bpm=120.0))
        # At y=0.80 (bottom) -> 1/1 whole note (0.5 Hz)
        name_bot, freq_bot = lfo.calculate_subdivision(0.80)
        self.assertEqual(name_bot, '1/1')
        self.assertAlmostEqual(freq_bot, 0.5, places=2)

        # At y=0.20 (top) -> 1/32 note (16 Hz)
        name_top, freq_top = lfo.calculate_subdivision(0.20)
        self.assertEqual(name_top, '1/32')
        self.assertAlmostEqual(freq_top, 16.0, places=2)

    def test_waveforms(self):
        lfo = GestureLFO()
        # Sine at phase 0 is 0, at pi/2 is 1.0, at 3*pi/2 is -1.0
        self.assertAlmostEqual(lfo.compute_wave(0.0, LFOWaveform.SINE), 0.0, places=3)
        self.assertAlmostEqual(lfo.compute_wave(3.14159 / 2, LFOWaveform.SINE), 1.0, places=3)

        # Square is +1 in first half, -1 in second half
        self.assertEqual(lfo.compute_wave(1.0, LFOWaveform.SQUARE), 1.0)
        self.assertEqual(lfo.compute_wave(4.0, LFOWaveform.SQUARE), -1.0)

        # Triangle at 0 is 0
        self.assertAlmostEqual(lfo.compute_wave(0.0, LFOWaveform.TRIANGLE), 0.0, places=3)

    def test_bpm_rescaling(self):
        lfo = GestureLFO(LFOConfig(bpm=120.0))
        _, f120 = lfo.calculate_subdivision(0.50)
        lfo.set_bpm(240.0)
        _, f240 = lfo.calculate_subdivision(0.50)
        self.assertAlmostEqual(f240, f120 * 2.0, places=2)

    def test_clutch_and_schema_validation(self):
        lfo = GestureLFO(LFOConfig(max_rate_hz=20.0))
        # Open arms
        lfo.update(0.5, pinch=0.5, tilt_depth=0.8, confidence=0.9, now=0.0, timestamp_ms=0)
        self.assertTrue(lfo.armed)
        self.assertFalse(lfo.active)

        # Pinch engages
        ev = lfo.update(0.5, pinch=0.2, tilt_depth=0.8, confidence=0.9, now=0.05, timestamp_ms=50)
        self.assertIsNotNone(ev)
        self.validator.validate(ev)
        self.assertEqual(ev['version'], 1)
        self.assertEqual(ev['source'], 'vision')
        self.assertEqual(ev['control'], 'filter')
        self.assertEqual(ev['type'], 'parameter')
        self.assertTrue(0.0 <= ev['value'] <= 1.0)


if __name__ == '__main__':
    unittest.main()
