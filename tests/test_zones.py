"""Tests for spatial performance zones and StrumGuard protection."""
import unittest
from vision.zones import Rect, StrumGuard


class RectTests(unittest.TestCase):
    def test_valid_rect(self):
        r = Rect(ymin=0.2, xmin=0.1, ymax=0.8, xmax=0.9)
        self.assertTrue(r.contains(0.5, 0.5))
        self.assertTrue(r.contains(0.1, 0.2))  # Edge
        self.assertFalse(r.contains(0.05, 0.5))
        self.assertFalse(r.contains(0.5, 0.95))

    def test_invalid_rect_bounds(self):
        with self.assertRaises(ValueError):
            Rect(ymin=0.8, xmin=0.1, ymax=0.2, xmax=0.9)
        with self.assertRaises(ValueError):
            Rect(ymin=0.2, xmin=0.9, ymax=0.8, xmax=0.1)
        with self.assertRaises(ValueError):
            Rect(ymin=-0.1, xmin=0.0, ymax=0.8, xmax=0.9)
        with self.assertRaises(ValueError):
            Rect(ymin=0.0, xmin=0.0, ymax=1.5, xmax=0.9)


class StrumGuardTests(unittest.TestCase):
    def test_default_strum_zone_suppression(self):
        guard = StrumGuard()
        # Bottom center is inside default strum zone
        suppressed, reason = guard.update(x=0.5, y=0.75, now=1.0)
        self.assertTrue(suppressed)
        self.assertEqual(reason, 'strum_zone')

        # Upper region is in air expression zone
        suppressed, reason = guard.update(x=0.5, y=0.25, now=2.0)
        self.assertFalse(suppressed)
        self.assertEqual(reason, 'expression_zone')

    def test_no_hand_handled_cleanly(self):
        guard = StrumGuard()
        suppressed, reason = guard.update(x=None, y=None, now=1.0)
        self.assertFalse(suppressed)
        self.assertEqual(reason, 'no_hand')

    def test_strum_motion_reversal_detection(self):
        # Create a guard with a strum zone placed elsewhere to isolate motion detection
        far_zone = Rect(ymin=0.8, xmin=0.8, ymax=0.9, xmax=0.9)
        guard = StrumGuard(strum_zone=far_zone, reversal_window=0.5, reversal_count_trigger=3)

        # Simulate 4 rapid strumming reversals in air (down-up-down-up)
        # 1. Down stroke
        guard.update(x=0.3, y=0.2, now=0.0)
        guard.update(x=0.3, y=0.5, now=0.05)  # vel_y = +6.0
        # 2. Up stroke
        guard.update(x=0.3, y=0.2, now=0.10)  # reversal 1, vel_y = -6.0
        # 3. Down stroke
        guard.update(x=0.3, y=0.5, now=0.15)  # reversal 2, vel_y = +6.0
        # 4. Up stroke
        suppressed, reason = guard.update(x=0.3, y=0.2, now=0.20)  # reversal 3 -> trigger!

        self.assertTrue(suppressed)
        self.assertEqual(reason, 'strum_motion')
        self.assertTrue(guard.strumming_detected)

    def test_slow_expressive_motion_is_not_flagged_as_strumming(self):
        far_zone = Rect(ymin=0.8, xmin=0.8, ymax=0.9, xmax=0.9)
        guard = StrumGuard(strum_zone=far_zone, reversal_window=0.5, reversal_count_trigger=3)

        # Slow smooth gesture sweeps
        guard.update(x=0.3, y=0.2, now=0.0)
        guard.update(x=0.3, y=0.22, now=0.2)
        guard.update(x=0.3, y=0.24, now=0.4)
        suppressed, reason = guard.update(x=0.3, y=0.22, now=0.6)

        self.assertFalse(suppressed)
        self.assertEqual(reason, 'expression_zone')
        self.assertFalse(guard.strumming_detected)
