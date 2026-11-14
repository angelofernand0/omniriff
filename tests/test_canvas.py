"""Tests for Air FX Spatial Canvas (vision/canvas.py)."""
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from vision.canvas import CanvasConfig, CornerPreset, SpatialCanvasController


class SpatialCanvasTests(unittest.TestCase):
    def setUp(self):
        schema_path = Path(__file__).resolve().parents[1] / 'protocol/control.schema.json'
        self.schema = json.loads(schema_path.read_text())
        self.validator = Draft202012Validator(self.schema)

    def test_corner_interpolation_exact(self):
        cfg = CanvasConfig(
            xmin=0.0, xmax=1.0, ymin=0.0, ymax=1.0,
            top_left=CornerPreset('TL', 1.0, 0.8),
            top_right=CornerPreset('TR', 0.9, 0.1),
            bottom_left=CornerPreset('BL', 0.2, 0.7),
            bottom_right=CornerPreset('BR', 0.3, 0.0),
        )
        ctrl = SpatialCanvasController(cfg)

        # Top-left (x=0, y=0)
        f, r, quad = ctrl.interpolate(0.0, 0.0)
        self.assertAlmostEqual(f, 1.0, places=2)
        self.assertAlmostEqual(r, 0.8, places=2)
        self.assertEqual(quad, 'TL')

        # Top-right (x=1, y=0)
        f, r, quad = ctrl.interpolate(1.0, 0.0)
        self.assertAlmostEqual(f, 0.9, places=2)
        self.assertAlmostEqual(r, 0.1, places=2)
        self.assertEqual(quad, 'TR')

        # Bottom-left (x=0, y=1)
        f, r, quad = ctrl.interpolate(0.0, 1.0)
        self.assertAlmostEqual(f, 0.2, places=2)
        self.assertAlmostEqual(r, 0.7, places=2)
        self.assertEqual(quad, 'BL')

        # Bottom-right (x=1, y=1)
        f, r, quad = ctrl.interpolate(1.0, 1.0)
        self.assertAlmostEqual(f, 0.3, places=2)
        self.assertAlmostEqual(r, 0.0, places=2)
        self.assertEqual(quad, 'BR')

        # Center (x=0.5, y=0.5)
        f, r, _ = ctrl.interpolate(0.5, 0.5)
        self.assertAlmostEqual(f, (1.0 + 0.9 + 0.2 + 0.3) / 4.0, places=2)
        self.assertAlmostEqual(r, (0.8 + 0.1 + 0.7 + 0.0) / 4.0, places=2)

    def test_out_of_bounds_clamping(self):
        ctrl = SpatialCanvasController()
        # Far outside canvas should clamp cleanly without crashing
        f1, r1, _ = ctrl.interpolate(-5.0, -10.0)
        self.assertTrue(0.0 <= f1 <= 1.0)
        self.assertTrue(0.0 <= r1 <= 1.0)

        f2, r2, _ = ctrl.interpolate(10.0, 5.0)
        self.assertTrue(0.0 <= f2 <= 1.0)
        self.assertTrue(0.0 <= r2 <= 1.0)

    def test_clutch_and_schema_validation(self):
        ctrl = SpatialCanvasController(CanvasConfig(pair_rate=10.0))

        # Open hand arms
        evs0 = ctrl.update(0.5, 0.3, pinch=0.5, confidence=0.9, now=0.0, timestamp_ms=0)
        self.assertEqual(evs0, [])
        self.assertTrue(ctrl.armed)
        self.assertFalse(ctrl.active)

        # Pinch engages and emits pair
        evs1 = ctrl.update(0.5, 0.3, pinch=0.2, confidence=0.9, now=0.15, timestamp_ms=150)
        self.assertEqual(len(evs1), 2)
        self.assertTrue(ctrl.active)

        for ev in evs1:
            self.validator.validate(ev)
            self.assertEqual(ev['version'], 1)
            self.assertEqual(ev['source'], 'vision')
            self.assertIn(ev['control'], ('filter', 'reverb'))

    def test_release_holds_last_value(self):
        ctrl = SpatialCanvasController()
        ctrl.update(0.5, 0.3, pinch=0.5, confidence=0.9, now=0.0, timestamp_ms=0)
        ctrl.update(0.5, 0.3, pinch=0.2, confidence=0.9, now=0.12, timestamp_ms=120)

        # Open hand disarms (release hold)
        evs_release = ctrl.update(0.8, 0.1, pinch=0.5, confidence=0.9, now=0.25, timestamp_ms=250)
        self.assertEqual(evs_release, [])
        self.assertFalse(ctrl.active)


if __name__ == '__main__':
    unittest.main()
