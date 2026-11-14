"""Tests for 3D hand orientation and dual-axis gesture control."""
import json
import math
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from vision.expressive import (
    DualAxisController,
    OrientationResult,
    compute_hand_orientation,
)


class MockPoint:
    def __init__(self, x, y, z=0.0):
        self.x = x
        self.y = y
        self.z = z


def make_hand(roll_deg=0.0, wrist_y=0.7, scale=0.1):
    """Generate 21 synthetic hand landmarks with a specified knuckle roll angle."""
    pts = [MockPoint(0.5, wrist_y, 0.0) for _ in range(21)]
    # Wrist is index 0
    pts[0] = MockPoint(0.5, wrist_y, 0.0)
    # Middle MCP is index 9 (above wrist)
    pts[9] = MockPoint(0.5, wrist_y - scale, 0.0)
    # Fingertip is index 12
    pts[12] = MockPoint(0.5, wrist_y - 2 * scale, 0.0)

    # Knuckle line: Index MCP (5) to Pinky MCP (17)
    rad = math.radians(roll_deg)
    half_w = scale * 0.8
    # 5 is left of knuckle center, 17 is right of knuckle center
    pts[5] = MockPoint(0.5 - half_w * math.cos(rad), (wrist_y - scale) - half_w * math.sin(rad), 0.0)
    pts[17] = MockPoint(0.5 + half_w * math.cos(rad), (wrist_y - scale) + half_w * math.sin(rad), 0.0)
    return pts


class OrientationTests(unittest.TestCase):
    def test_horizontal_hand_has_zero_roll(self):
        hand = make_hand(roll_deg=0.0)
        orient = compute_hand_orientation(hand)
        self.assertIsNotNone(orient)
        self.assertAlmostEqual(orient.roll_deg, 0.0, delta=2.0)
        self.assertAlmostEqual(orient.tilt_amount, 0.0, delta=0.05)
        self.assertGreater(orient.openness, 0.0)

    def test_tilted_hand_measures_roll_and_tilt(self):
        hand_30 = make_hand(roll_deg=30.0)
        orient_30 = compute_hand_orientation(hand_30)
        self.assertIsNotNone(orient_30)
        self.assertAlmostEqual(orient_30.roll_deg, 30.0, delta=2.0)
        self.assertAlmostEqual(orient_30.tilt_amount, 0.5, delta=0.05)

        hand_60 = make_hand(roll_deg=60.0)
        orient_60 = compute_hand_orientation(hand_60)
        self.assertIsNotNone(orient_60)
        self.assertAlmostEqual(orient_60.tilt_amount, 1.0, delta=0.05)

    def test_invalid_landmarks_fail_closed(self):
        self.assertIsNone(compute_hand_orientation([]))
        self.assertIsNone(compute_hand_orientation([MockPoint(0, 0)] * 10))


class DualAxisControllerTests(unittest.TestCase):
    def setUp(self):
        schema_path = Path(__file__).resolve().parents[1] / 'protocol/control.schema.json'
        self.validator = Draft202012Validator(json.loads(schema_path.read_text()))

    def test_open_pinch_clutch_and_dual_parameter_emission(self):
        # 10 pairs/sec = 20 events/sec total
        ctrl = DualAxisController(pair_rate=10, deadband=0.01)

        # 1. Arm with open hand
        orient = OrientationResult(roll_deg=0.0, pitch_deg=0.0, tilt_amount=0.0, openness=0.8)
        events = ctrl.update(y=0.8, pinch=0.6, orientation=orient, confidence=0.9, now=0.0, timestamp_ms=0)
        self.assertEqual(events, [])
        self.assertTrue(ctrl.armed)
        self.assertFalse(ctrl.active)

        # 2. Pinch to engage (elevation at bottom y=0.8 -> filter=0.0, tilt=0.0 -> reverb=0.0)
        events = ctrl.update(y=0.8, pinch=0.2, orientation=orient, confidence=0.9, now=0.10, timestamp_ms=100)
        self.assertTrue(ctrl.active)
        self.assertEqual(len(events), 2)
        for ev in events:
            self.validator.validate(ev)

        self.assertEqual(events[0]['control'], 'filter')
        self.assertEqual(events[1]['control'], 'reverb')
        self.assertEqual(events[0]['seq'], 0)
        self.assertEqual(events[1]['seq'], 1)

        # 3. Elevate hand (y=0.2 -> high filter) and tilt hand (tilt=0.6 -> high reverb)
        tilted = OrientationResult(roll_deg=36.0, pitch_deg=0.0, tilt_amount=0.6, openness=0.2)
        events = ctrl.update(y=0.2, pinch=0.2, orientation=tilted, confidence=0.9, now=0.25, timestamp_ms=250)
        self.assertEqual(len(events), 2)
        for ev in events:
            self.validator.validate(ev)

        filter_ev = next(e for e in events if e['control'] == 'filter')
        reverb_ev = next(e for e in events if e['control'] == 'reverb')

        self.assertGreater(filter_ev['value'], 0.5)
        self.assertGreater(reverb_ev['value'], 0.3)
        self.assertEqual(filter_ev['seq'], 2)
        self.assertEqual(reverb_ev['seq'], 3)

    def test_rearm_clears_output(self):
        ctrl = DualAxisController()
        orient = OrientationResult(roll_deg=0.0, pitch_deg=0.0, tilt_amount=0.0, openness=0.8)
        ctrl.update(y=0.8, pinch=0.6, orientation=orient, confidence=0.9, now=0.0, timestamp_ms=0)
        ctrl.update(y=0.5, pinch=0.2, orientation=orient, confidence=0.9, now=0.15, timestamp_ms=150)
        self.assertTrue(ctrl.active)

        ctrl.rearm()
        self.assertFalse(ctrl.active)
        self.assertFalse(ctrl.armed)
        self.assertIsNone(ctrl.primary_val)
        self.assertIsNone(ctrl.secondary_val)
