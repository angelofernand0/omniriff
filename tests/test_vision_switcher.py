"""Unit tests for EffectSwitcher."""
import unittest

from vision.control import Controller
from vision.switcher import EffectSwitcher


class TestEffectSwitcher(unittest.TestCase):
    def test_initial_state(self):
        switcher = EffectSwitcher(['filter', 'reverb'])
        self.assertEqual(switcher.current_control, 'filter')
        self.assertFalse(switcher.latched)

    def test_single_control_fails(self):
        with self.assertRaises(ValueError):
            EffectSwitcher(['filter'])

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

    def test_low_confidence_resets_touch(self):
        controller = Controller(control='filter')
        switcher = EffectSwitcher(['filter', 'reverb'], hold_seconds=0.20, min_confidence=0.6)

        switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.0, controller=controller)
        # Low confidence frame
        switcher.update(pinky_pinch=0.20, confidence=0.4, now=1.1, controller=controller)
        # Re-enters at t=1.2s (only 0.0s elapsed since reset)
        switched = switcher.update(pinky_pinch=0.20, confidence=0.8, now=1.2, controller=controller)
        self.assertFalse(switched)
        self.assertEqual(switcher.current_control, 'filter')

    def test_cli_args_parsing(self):
        import argparse
        from unittest.mock import patch
        import sys

        # Test parser behavior on vision CLI
        from vision.__main__ import main
        # When combined with scene, should error
        with self.assertRaises(SystemExit):
            main(['--model', 'dummy.task', '--gesture-switch', '--scene', 'bloom'])


if __name__ == '__main__':
    unittest.main()
