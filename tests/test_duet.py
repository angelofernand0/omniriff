"""Tests for Duet & Collaborative Two-Hand Controller (vision/duet.py)."""
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from vision.duet import DuetController


class DuetControllerTests(unittest.TestCase):
    def setUp(self):
        schema_path = Path(__file__).resolve().parents[1] / 'protocol/control.schema.json'
        self.schema = json.loads(schema_path.read_text())
        self.validator = Draft202012Validator(self.schema)

    def test_left_right_spatial_sorting(self):
        ctrl = DuetController()
        # Pass Hand B on left (x=0.2) and Hand A on right (x=0.8)
        # Sorted hands should assign x=0.2 to Hand A (Filter) and x=0.8 to Hand B (Reverb)
        # Arm both
        ctrl.update_duet([(0.8, 0.5, 0.5, 0.9), (0.2, 0.5, 0.5, 0.9)], now=0.0, timestamp_ms=0)
        # Engage both
        evs = ctrl.update_duet([(0.8, 0.5, 0.2, 0.9), (0.2, 0.5, 0.2, 0.9)], now=0.05, timestamp_ms=50)

        # Hand at x=0.2 should control filter, hand at x=0.8 should control reverb
        self.assertEqual(ctrl.channel_a.control, 'filter')
        self.assertEqual(ctrl.channel_b.control, 'reverb')

    def test_single_hand_keeps_secondary_dormant(self):
        ctrl = DuetController()
        # Only 1 hand present
        ctrl.update_duet([(0.5, 0.5, 0.5, 0.9)], now=0.0, timestamp_ms=0)
        evs = ctrl.update_duet([(0.5, 0.5, 0.2, 0.9)], now=0.15, timestamp_ms=150)

        self.assertTrue(ctrl.channel_a.active)
        self.assertFalse(ctrl.channel_b.active)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]['control'], 'filter')

    def test_schema_compliance_of_dual_envelopes(self):
        ctrl = DuetController()
        # Arm & engage both
        ctrl.update_duet([(0.3, 0.6, 0.5, 0.9), (0.7, 0.4, 0.5, 0.9)], now=0.0, timestamp_ms=0)
        evs = ctrl.update_duet([(0.3, 0.6, 0.2, 0.9), (0.7, 0.4, 0.2, 0.9)], now=0.15, timestamp_ms=150)

        self.assertEqual(len(evs), 2)
        for ev in evs:
            self.validator.validate(ev)
            self.assertEqual(ev['version'], 1)
            self.assertEqual(ev['source'], 'vision')
            self.assertEqual(ev['type'], 'parameter')
            self.assertIn(ev['control'], ('filter', 'reverb'))

    def test_different_controls_required(self):
        with self.assertRaises(ValueError):
            DuetController(hand_a_control='filter', hand_b_control='filter')


if __name__ == '__main__':
    unittest.main()
