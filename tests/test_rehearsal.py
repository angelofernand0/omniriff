"""Tests for Automated Rehearsal & Pre-Show Calibration Studio (vision/rehearsal.py)."""
import json
from pathlib import Path
import tempfile
import unittest

from vision.rehearsal import RehearsalStudio, run_demo_rehearsal
from vision.zones import Rect


class RehearsalStudioTests(unittest.TestCase):
    def test_reach_calibration_with_padding(self):
        studio = RehearsalStudio()
        # Feed samples spanning exactly 0.20 (top) to 0.80 (bottom)
        for i in range(21):
            studio.feed_reach_sample(0.20 + (i / 20.0) * 0.60)

        high, low = studio.finalize_reach()
        # High should be slightly padded below min_y (0.20 + 0.05*0.60 = 0.23)
        self.assertAlmostEqual(high, 0.23, places=2)
        # Low should be slightly padded above max_y (0.80 - 0.05*0.60 = 0.77)
        self.assertAlmostEqual(low, 0.77, places=2)

    def test_reach_sparse_samples_fallback(self):
        studio = RehearsalStudio()
        studio.feed_reach_sample(0.5)
        high, low = studio.finalize_reach()
        self.assertEqual(high, 0.20)
        self.assertEqual(low, 0.80)

    def test_clutch_hysteresis_verification(self):
        studio = RehearsalStudio()
        # Valid sequence: open -> pinch
        seq_valid = [(0.0, 0.50), (0.2, 0.46), (0.4, 0.20)]
        self.assertTrue(studio.test_clutch_hysteresis(seq_valid))

        # Invalid sequence: never opened
        seq_invalid = [(0.0, 0.30), (0.2, 0.20)]
        self.assertFalse(studio.test_clutch_hysteresis(seq_invalid))

    def test_strumguard_isolation_suppresses_strums(self):
        studio = RehearsalStudio()
        # Strumming points deep inside strum zone (y = 0.70)
        strum_pts = [(i * 0.033, 0.40, 0.70) for i in range(15)]
        suppressed, fp, passed = studio.test_strumguard_isolation(strum_pts)
        self.assertEqual(fp, 0)
        self.assertGreater(suppressed, 0)
        self.assertTrue(passed)

    def test_export_calibration_refuses_overwrite_without_flag(self):
        studio = RehearsalStudio()
        studio.calibrated_high = 0.25
        studio.calibrated_low = 0.75

        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / 'calibration.json'
            studio.export_calibration(out_file)
            self.assertTrue(out_file.exists())

            # Attempting to export again without overwrite must raise FileExistsError
            with self.assertRaises(FileExistsError):
                studio.export_calibration(out_file, overwrite=False)

            # With overwrite=True it succeeds
            studio.calibrated_high = 0.22
            studio.export_calibration(out_file, overwrite=True)
            data = json.loads(out_file.read_text())
            self.assertEqual(data['high'], 0.22)

    def test_run_demo_rehearsal_end_to_end(self):
        rep = run_demo_rehearsal()
        self.assertTrue(rep.ready_for_stage)
        self.assertTrue(rep.clutch_passed)
        self.assertTrue(rep.strumguard_passed)
        self.assertIn(rep.gesture_grade, ('S', 'A'))
        self.assertGreaterEqual(rep.gesture_score, 85)

        # Check JSON serialization
        rep_json = rep.to_json()
        parsed = json.loads(rep_json)
        self.assertEqual(parsed['version'], 1)
        self.assertTrue(parsed['ready_for_stage'])


if __name__ == '__main__':
    unittest.main()
