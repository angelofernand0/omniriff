"""Unit tests for EffectSwitcher."""
import math
import unittest

from vision.control import Controller
from vision.switcher import EffectSwitcher


class TestEffectSwitcher(unittest.TestCase):
    def test_initial_state(self):
        switcher = EffectSwitcher(['filter', 'reverb'])
        self.assertEqual(switcher.current_control, 'filter')
        self.assertFalse(switcher.latched)

    def test_invalid_settings_rejected(self):
        with self.assertRaises(ValueError):
            EffectSwitcher(['filter'])
        with self.assertRaises(ValueError):
            EffectSwitcher(['filter', 'reverb'], hold_seconds=0)
        with self.assertRaises(ValueError):
            EffectSwitcher(['filter', 'reverb'], hold_seconds=-0.1)
        with self.assertRaises(ValueError):
            EffectSwitcher(['filter', 'reverb'], hold_seconds=float('nan'))
        with self.assertRaises(ValueError):
            EffectSwitcher(['filter', 'reverb'], min_confidence=float('nan'))
        with self.assertRaises(ValueError):
            EffectSwitcher(['filter', 'reverb'], min_confidence=1.5)
        with self.assertRaises(ValueError):
            EffectSwitcher(['filter', 'reverb'], touch_threshold=0.5, release_threshold=0.4)

    def test_switch_after_hold_duration(self):
        controller = Controller(control='filter')
        switcher = EffectSwitcher(['filter', 'reverb'], hold_seconds=0.20)

        # Frame 1: Touch begins at t=1.0s
        switched = switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.0, controller=controller)
        self.assertFalse(switched)
        self.assertEqual(switcher.current_control, 'filter')
        self.assertEqual(controller.control, 'filter')

        # Frame 2: Touch continuing at t=1.1s (0.1s elapsed < 0.2s)
        switched = switcher.update(pinky_pinch=0.22, confidence=0.8, now=1.1, controller=controller)
        self.assertFalse(switched)
        self.assertEqual(switcher.current_control, 'filter')

        # Frame 3: Touch reaches t=1.20s (0.2s elapsed) -> triggers switch!
        switched = switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.20, controller=controller)
        self.assertTrue(switched)
        self.assertEqual(switcher.current_control, 'reverb')
        self.assertEqual(controller.control, 'reverb')
        self.assertTrue(switcher.latched)

    def test_latch_requires_release(self):
        controller = Controller(control='filter')
        switcher = EffectSwitcher(['filter', 'reverb'], hold_seconds=0.20)

        # Trigger switch
        switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.0, controller=controller)
        switched = switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.21, controller=controller)
        self.assertTrue(switched)
        self.assertEqual(switcher.current_control, 'reverb')

        # While still held at t=1.5s, no second switch occurs
        switched = switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.50, controller=controller)
        self.assertFalse(switched)
        self.assertEqual(switcher.current_control, 'reverb')

        # Release hand at t=1.6s
        switched = switcher.update(pinky_pinch=0.50, confidence=0.8, now=1.60, controller=controller)
        self.assertFalse(switched)
        self.assertFalse(switcher.latched)

        # New touch at t=2.0s to 2.21s cycles back to filter
        switcher.update(pinky_pinch=0.20, confidence=0.8, now=2.0, controller=controller)
        switched = switcher.update(pinky_pinch=0.20, confidence=0.8, now=2.21, controller=controller)
        self.assertTrue(switched)
        self.assertEqual(switcher.current_control, 'filter')
        self.assertEqual(controller.control, 'filter')

    def test_brief_touch_does_not_switch(self):
        controller = Controller(control='filter')
        switcher = EffectSwitcher(['filter', 'reverb'], hold_seconds=0.20)

        # Touch at t=1.0s
        switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.0, controller=controller)
        # Release at t=1.1s before threshold
        switcher.update(pinky_pinch=0.48, confidence=0.8, now=1.1, controller=controller)

        # Still filter
        self.assertEqual(switcher.current_control, 'filter')
        self.assertEqual(controller.control, 'filter')

    def test_low_confidence_and_nan_resets_touch(self):
        controller = Controller(control='filter')
        switcher = EffectSwitcher(['filter', 'reverb'], hold_seconds=0.20, min_confidence=0.6)

        switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.0, controller=controller)
        # NaN confidence
        switched = switcher.update(pinky_pinch=0.20, confidence=float('nan'), now=1.1, controller=controller)
        self.assertFalse(switched)
        self.assertIsNone(switcher.touch_start)

        # Re-enters at t=1.2s
        switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.2, controller=controller)
        # Low confidence (<0.6)
        switched = switcher.update(pinky_pinch=0.20, confidence=0.5, now=1.3, controller=controller)
        self.assertFalse(switched)
        self.assertIsNone(switcher.touch_start)

    def test_suppression_resets_pending_dwell(self):
        controller = Controller(control='filter')
        switcher = EffectSwitcher(['filter', 'reverb'], hold_seconds=0.20)

        # Touch begins at t=1.0s
        switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.0, controller=controller, suppressed=False)
        self.assertEqual(switcher.touch_start, 1.0)

        # Suppressed frame at t=1.1s (e.g. StrumGuard active or expired frame)
        switched = switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.1, controller=controller, suppressed=True)
        self.assertFalse(switched)
        self.assertIsNone(switcher.touch_start)

        # Resumed at t=1.21s: dwell was wiped by suppression, so no switch triggers
        switched = switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.21, controller=controller, suppressed=False)
        self.assertFalse(switched)
        self.assertEqual(switcher.touch_start, 1.21)

    def test_relative_pickup_preserved_across_switches(self):
        """Relative pickup value must not jump or reset to 1/0 when switching back and forth."""
        controller = Controller(control='filter', relative=True)
        switcher = EffectSwitcher(['filter', 'reverb'], hold_seconds=0.20)

        # 1. Drive filter in relative mode: open hand (arm) then pinch
        controller.update(y=0.5, pinch=0.50, confidence=0.8, now=1.0, timestamp_ms=1000)
        self.assertTrue(controller.armed)
        self.assertFalse(controller.active)

        # Pinch engages at y=0.5. Default filter initial value is 1.0.
        controller.update(y=0.5, pinch=0.20, confidence=0.8, now=1.05, timestamp_ms=1050)
        self.assertTrue(controller.active)
        self.assertEqual(controller.pickup_value, 1.0)

        # Move wrist down to y=0.7 (relative change decreases value from 1.0)
        ev1 = controller.update(y=0.7, pinch=0.20, confidence=0.8, now=1.20, timestamp_ms=1200)
        self.assertIsNotNone(ev1)
        self.assertEqual(ev1['control'], 'filter')
        last_filter_value = controller.sent_value
        self.assertIsNotNone(last_filter_value)
        self.assertLess(last_filter_value, 1.0)

        # 2. Switch to reverb via pinky touch
        switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.30, controller=controller)
        switched = switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.51, controller=controller)
        self.assertTrue(switched)
        self.assertEqual(controller.control, 'reverb')
        # Re-arm required, no values emitted during switch
        self.assertFalse(controller.active)
        self.assertFalse(controller.armed)

        # 3. Release pinky
        switcher.update(pinky_pinch=0.50, confidence=0.8, now=1.55, controller=controller)

        # 4. Drive reverb in relative mode: open hand then pinch
        controller.update(y=0.4, pinch=0.50, confidence=0.8, now=1.60, timestamp_ms=1600)
        self.assertTrue(controller.armed)

        # Pinch at y=0.4. Default initial reverb is 0.0.
        controller.update(y=0.4, pinch=0.20, confidence=0.8, now=1.65, timestamp_ms=1650)
        self.assertTrue(controller.active)
        self.assertEqual(controller.pickup_value, 0.0)

        # Move wrist up to y=0.2 (increases reverb)
        ev2 = controller.update(y=0.2, pinch=0.20, confidence=0.8, now=1.80, timestamp_ms=1800)
        self.assertIsNotNone(ev2)
        self.assertEqual(ev2['control'], 'reverb')
        last_reverb_value = controller.sent_value
        self.assertIsNotNone(last_reverb_value)
        self.assertGreater(last_reverb_value, 0.0)

        # 5. Switch back to filter via pinky touch
        switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.90, controller=controller)
        switched = switcher.update(pinky_pinch=0.20, confidence=0.8, now=2.11, controller=controller)
        self.assertTrue(switched)
        self.assertEqual(controller.control, 'filter')
        # Controller sent_value for filter should be restored to last_filter_value!
        self.assertEqual(controller.sent_value, last_filter_value)

        # 6. Re-engage filter: open hand then pinch
        controller.update(y=0.3, pinch=0.50, confidence=0.8, now=2.20, timestamp_ms=2200)
        self.assertTrue(controller.armed)

        # Pinch at new position y=0.3
        controller.update(y=0.3, pinch=0.20, confidence=0.8, now=2.25, timestamp_ms=2250)
        self.assertTrue(controller.active)
        # CRUCIAL: pickup_value must be last_filter_value (~0.67), NOT reset to 1.0!
        self.assertEqual(controller.pickup_value, last_filter_value)

    def test_cli_args_parsing(self):
        from vision.__main__ import main
        # When combined with scene, should error
        with self.assertRaises(SystemExit):
            main(['--model', 'dummy.task', '--gesture-switch', '--scene', 'bloom'])
        # When combined with rehearsal, should error
        with self.assertRaises(SystemExit):
            main(['--model', 'dummy.task', '--gesture-switch', '--rehearsal'])


if __name__ == '__main__':
    unittest.main()
