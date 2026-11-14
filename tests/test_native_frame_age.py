"""Native main loop must not refresh old observations after slow inference."""
import unittest
from tests.test_native_strum_guard import run_trace


class NativeFrameAgeTests(unittest.TestCase):
    def test_slow_inference_cannot_emit_or_arm_then_held_pinch_is_blocked(self):
        trace=[(.4,.6,.95),(.4,.1,.95),(.35,.1,.95),(.35,.1,.95)]
        result=run_trace(trace,False,delays={1:.3})
        self.assertEqual(result.events,[])
        self.assertEqual(result.summary['expired_frames'],1)
        self.assertFalse(result.frames[1]['present'])
        self.assertEqual(result.frames[1]['landmarks'],[])
        self.assertFalse(result.frames[-1]['engaged'])
        self.assertEqual(len(result.rows[1]['hands']),2) # Historical metadata retains original capture clock.

    def test_fresh_open_and_pinch_recover_with_original_capture_timestamps(self):
        trace=[(.4,.6,.95),(.4,.1,.95),(.35,.1,.95),(.35,.6,.95),(.35,.1,.95)]
        result=run_trace(trace,False,delays={1:.3})
        self.assertEqual(len(result.events),1)
        self.assertTrue(result.frames[-1]['engaged'])
        self.assertEqual(result.events[0]['timestamp_ms'],result.rows[-1]['timestamp_ms'])

    def test_expired_open_hand_cannot_arm_a_later_pinch(self):
        result=run_trace([(.4,.6,.95),(.4,.1,.95),(.35,.1,.95)],False,delays={0:.3})
        self.assertEqual(result.events,[])
        self.assertFalse(result.frames[-1]['engaged'])

    def test_timely_inference_retains_capture_stamp_instead_of_rebasing(self):
        result=run_trace([(.4,.6,.95),(.4,.1,.95)],False,delays={1:.1})
        self.assertEqual(len(result.events),1)
        self.assertEqual(result.events[0]['timestamp_ms'],result.rows[1]['timestamp_ms'])
        self.assertEqual(result.summary['expired_frames'],0)
