"""Unit tests for the expressive gesture looper."""
import json
from pathlib import Path
import tempfile
import unittest

from vision.looper import GestureLooper, LoopState


class GestureLooperTests(unittest.TestCase):

    def test_initialization_validation(self):
        # Valid duration
        looper = GestureLooper(duration_s=2.5)
        self.assertEqual(looper.duration_s, 2.5)
        self.assertEqual(looper.state, LoopState.IDLE)

        # BPM and bars calculation (120 BPM, 2 bars of 4/4 = 4.0s)
        looper_bpm = GestureLooper(bpm=120.0, bars=2)
        self.assertAlmostEqual(looper_bpm.duration_s, 4.0)

        # Invalid durations
        with self.assertRaises(ValueError):
            GestureLooper(duration_s=-1.0)
        with self.assertRaises(ValueError):
            GestureLooper(duration_s=float('nan'))
        with self.assertRaises(ValueError):
            GestureLooper(bpm=-50.0, bars=1)
        with self.assertRaises(ValueError):
            GestureLooper(bpm=120.0, bars=0)

    def test_record_and_sample_single_parameter(self):
        looper = GestureLooper(duration_s=2.0)
        looper.start_recording(t0=100.0)
        self.assertTrue(looper.is_recording)

        # Record frames: ramp filter from 0.2 up to 0.8
        looper.record_frame(100.0, {'filter': 0.2})
        looper.record_frame(100.5, {'filter': 0.4})
        looper.record_frame(101.0, {'filter': 0.6})
        looper.record_frame(101.5, {'filter': 0.8})
        # Final frame at t=102.0 triggers auto-finish
        auto_finished = looper.record_frame(102.0, {'filter': 0.8})

        self.assertTrue(auto_finished)
        self.assertTrue(looper.is_playing)
        self.assertEqual(looper.state, LoopState.PLAYING)

        # Sampling at playback start (t=102.0 -> cycle offset 0.0)
        p0 = looper.sample(102.0)
        self.assertIsNotNone(p0)
        self.assertAlmostEqual(p0['filter'], 0.2, places=2)

        # Sampling midway (cycle offset 0.5)
        p_mid = looper.sample(102.5)
        self.assertIsNotNone(p_mid)
        self.assertAlmostEqual(p_mid['filter'], 0.4, places=2)

        # Sampling at next cycle (t=104.5 -> cycle offset 0.5)
        p_next_cycle = looper.sample(104.5)
        self.assertIsNotNone(p_next_cycle)
        self.assertAlmostEqual(p_next_cycle['filter'], 0.4, places=2)

    def test_multi_parameter_scene_looping(self):
        # Dual-parameter Scene Morph: filter & reverb
        looper = GestureLooper(duration_s=1.0)
        looper.start_recording(t0=0.0)

        looper.record_frame(0.0, {'filter': 1.0, 'reverb': 0.0})
        looper.record_frame(0.5, {'filter': 0.7, 'reverb': 0.3})
        looper.record_frame(1.0, {'filter': 0.4, 'reverb': 0.8})

        self.assertTrue(looper.is_playing)

        # Midpoint interpolation
        sampled = looper.sample(1.25)  # cycle offset 0.25
        self.assertIsNotNone(sampled)
        self.assertIn('filter', sampled)
        self.assertIn('reverb', sampled)
        self.assertAlmostEqual(sampled['filter'], 0.85, places=2)
        self.assertAlmostEqual(sampled['reverb'], 0.15, places=2)

    def test_cyclic_crossfade_continuity(self):
        # Start at 0.1, end at 0.9. Cyclic crossfade should smoothly blend end toward 0.1
        looper = GestureLooper(duration_s=2.0, crossfade_s=0.2)
        looper.start_recording(t0=0.0)

        looper.record_frame(0.0, {'filter': 0.1})
        looper.record_frame(1.0, {'filter': 0.5})
        looper.record_frame(1.7, {'filter': 0.9})
        looper.record_frame(1.9, {'filter': 0.9})
        looper.record_frame(2.0, {'filter': 0.9})

        self.assertTrue(looper.is_playing)

        start_val = looper.sample(2.0)['filter']
        end_val = looper.sample(3.999)['filter']

        # End of loop cycle must be close to start value due to crossfade
        self.assertAlmostEqual(start_val, 0.1, places=1)
        self.assertAlmostEqual(end_val, 0.1, places=1)

    def test_punch_in_and_punch_out(self):
        looper = GestureLooper(duration_s=2.0)
        looper.start_recording(t0=0.0)
        looper.record_frame(0.0, {'filter': 0.3})
        looper.record_frame(2.0, {'filter': 0.3})

        self.assertEqual(looper.state, LoopState.PLAYING)
        self.assertAlmostEqual(looper.sample(2.5)['filter'], 0.3)

        # Punch in live control at t=3.0 with filter=0.95
        looper.punch_in(3.0, {'filter': 0.95})
        self.assertEqual(looper.state, LoopState.PUNCHED_IN)
        self.assertAlmostEqual(looper.sample(3.2)['filter'], 0.95)

        # Update punch in
        looper.update_punch_in({'filter': 0.80})
        self.assertAlmostEqual(looper.sample(3.4)['filter'], 0.80)

        # Punch out returns to loop value
        looper.punch_out(3.5)
        self.assertEqual(looper.state, LoopState.PLAYING)
        self.assertAlmostEqual(looper.sample(3.6)['filter'], 0.3)

    def test_export_take_jsonl(self):
        looper = GestureLooper(duration_s=1.0, target_rate_hz=10.0)
        looper.start_recording(t0=0.0)
        looper.record_frame(0.0, {'filter': 0.2, 'reverb': 0.5})
        looper.record_frame(1.0, {'filter': 0.8, 'reverb': 0.1})

        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / "take.jsonl"
            count = looper.export_take_jsonl(out_file, repetitions=2)

            self.assertTrue(out_file.exists())
            self.assertGreater(count, 0)

            # Read back lines and verify schema compliance
            lines = out_file.read_text().strip().split('\n')
            self.assertEqual(len(lines), count)

            prev_ts = -1.0
            prev_seq = 0

            for line in lines:
                event = json.loads(line)
                self.assertEqual(event['version'], 1)
                self.assertEqual(event['source'], 'vision')
                self.assertIn(event['action'], ('filter', 'reverb'))
                self.assertGreaterEqual(event['value'], 0.0)
                self.assertLessEqual(event['value'], 1.0)
                self.assertGreater(event['sequence'], prev_seq)
                self.assertGreaterEqual(event['timestamp'], prev_ts)

                prev_seq = event['sequence']
                prev_ts = event['timestamp']

            # Overwrite protection
            with self.assertRaises(FileExistsError):
                looper.export_take_jsonl(out_file, repetitions=1)


if __name__ == '__main__':
    unittest.main()
