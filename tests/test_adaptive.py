"""Tests for Adaptive Difficulty & Accessibility Engine (vision/adaptive.py)."""
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from vision.adaptive import AdaptiveController, AssistiveProfile


class AdaptiveControllerTests(unittest.TestCase):
    def setUp(self):
        schema_path = Path(__file__).resolve().parents[1] / 'protocol/control.schema.json'
        self.schema = json.loads(schema_path.read_text())
        self.validator = Draft202012Validator(self.schema)

    def test_schema_compliance_of_emitted_events(self):
        ctrl = AdaptiveController(rate=20.0, control='filter')
        # Arm
        ctrl.update(y=0.5, pinch=0.5, confidence=0.9, now=0.0, timestamp_ms=0)
        # Engage
        ev = ctrl.update(y=0.5, pinch=0.2, confidence=0.9, now=0.05, timestamp_ms=50)
        self.assertIsNotNone(ev)
        self.validator.validate(ev)
        self.assertEqual(ev['control'], 'filter')
        self.assertEqual(ev['source'], 'vision')

    def test_auto_gamut_expansion_for_limited_mobility(self):
        # A user who can only move between y=0.60 and y=0.50 (a 10cm range)
        profile = AssistiveProfile(auto_range=True, magnetic_snap=False, base_tau=0.01)
        ctrl = AdaptiveController(profile=profile, rate=60.0)

        # Arm & engage at 0.60
        ctrl.update(y=0.60, pinch=0.5, confidence=0.9, now=0.0, timestamp_ms=0)
        ctrl.update(y=0.60, pinch=0.2, confidence=0.9, now=0.02, timestamp_ms=20)

        # Feed a sequence between 0.60 (low reach) and 0.50 (high reach)
        for i in range(20):
            t = 0.04 + i * 0.02
            y_pos = 0.60 if i % 2 == 0 else 0.50
            ev = ctrl.update(y=y_pos, pinch=0.2, confidence=0.9, now=t, timestamp_ms=int(t * 1000))

        # Check observed bounds adapted
        self.assertLessEqual(ctrl.observed_max_y, 0.50)
        self.assertGreaterEqual(ctrl.observed_min_y, 0.60)

    def test_magnetic_snapping_near_target(self):
        # When value is within snap radius of 0.5, it snaps towards 0.5
        profile = AssistiveProfile(
            auto_range=False,
            magnetic_snap=True,
            snap_targets=(0.5,),
            snap_radius=0.05,
            base_tau=0.001,  # immediate response
        )
        ctrl = AdaptiveController(profile=profile, rate=60.0)
        ctrl.update(y=0.5, pinch=0.5, confidence=0.9, now=0.0, timestamp_ms=0)
        # Position calibrated for ~0.50 (between 0.80 and 0.20: y=0.50 is exact center)
        # Let's slightly perturb to 0.51 -> raw target is (0.80 - 0.51) / 0.60 = 0.4833
        # With snap target 0.50 and radius 0.05, it should be pulled closer to 0.50
        ev = ctrl.update(y=0.505, pinch=0.2, confidence=0.9, now=0.05, timestamp_ms=50)
        self.assertIsNotNone(ev)
        val = ev['value']
        # Without snap: (0.80 - 0.505) / 0.60 = 0.4916
        # With snap: attracted closer to 0.50
        self.assertAlmostEqual(val, 0.50, delta=0.02)

    def test_tremor_increases_filtering_tau(self):
        profile = AssistiveProfile(tremor_filter=True, base_tau=0.05, max_tau=0.35)
        ctrl = AdaptiveController(profile=profile, rate=60.0)

        ctrl.update(y=0.5, pinch=0.5, confidence=0.9, now=0.0, timestamp_ms=0)
        ctrl.update(y=0.5, pinch=0.2, confidence=0.9, now=0.02, timestamp_ms=20)

        # Feed rapid oscillating tremor (alternating directions)
        t = 0.04
        for i in range(12):
            y_tremor = 0.50 + (0.04 if i % 2 == 0 else -0.04)
            ctrl.update(y=y_tremor, pinch=0.2, confidence=0.9, now=t, timestamp_ms=int(t * 1000))
            t += 0.02

        # Check that current tau has elevated to max_tau
        self.assertGreater(ctrl._current_tau, profile.base_tau)
        self.assertAlmostEqual(ctrl._current_tau, profile.max_tau, places=2)


if __name__ == '__main__':
    unittest.main()
