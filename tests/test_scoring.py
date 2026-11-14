"""Tests for Gesture Scoring & Analytics (vision/scoring.py)."""
import json
import math
import unittest

from vision.scoring import GestureScoreReport, GestureScorer, ScoreBreakdown


class GestureScoringTests(unittest.TestCase):
    def test_insufficient_samples(self):
        scorer = GestureScorer()
        scorer.add_sample(0.1, 0.5)
        scorer.add_sample(0.2, 0.6)
        report = scorer.evaluate()
        self.assertIn('Insufficient gesture data', report.summary)
        self.assertEqual(report.overall_score, 0)

    def test_smooth_sinusoidal_gesture_scores_high(self):
        scorer = GestureScorer()
        # Generate 3 seconds of a clean, smooth 0.5 Hz sweep across [0.05, 0.95]
        fps = 30.0
        for i in range(90):
            t = i / fps
            val = 0.5 + 0.45 * math.sin(2 * math.pi * 0.5 * t)
            scorer.add_sample(t, val, (0.5, 0.5))

        report = scorer.evaluate()
        self.assertGreaterEqual(report.overall_score, 85)
        self.assertIn(report.letter_grade, ('A', 'S'))
        self.assertGreaterEqual(report.breakdown.smoothness, 80.0)
        self.assertGreaterEqual(report.breakdown.range_coverage, 90.0)
        self.assertIn('Superb gestural control', report.actionable_tips[0])

    def test_jittery_erratic_gesture_low_smoothness(self):
        scorer = GestureScorer()
        # High-frequency alternating values simulate severe tremor/jitter
        fps = 30.0
        for i in range(60):
            t = i / fps
            val = 0.5 + (0.3 if i % 2 == 0 else -0.3)
            scorer.add_sample(t, val)

        report = scorer.evaluate()
        self.assertLess(report.breakdown.smoothness, 50.0)
        self.assertIn('Smooth out hand acceleration', ' '.join(report.actionable_tips))

    def test_narrow_gamut_flags_range_tip(self):
        scorer = GestureScorer()
        # Smooth but confined to a tiny range [0.48, 0.52]
        fps = 30.0
        for i in range(60):
            t = i / fps
            val = 0.50 + 0.02 * math.sin(t)
            scorer.add_sample(t, val)

        report = scorer.evaluate()
        self.assertLess(report.breakdown.range_coverage, 20.0)
        self.assertIn('Widen your gesture reach', ' '.join(report.actionable_tips))

    def test_reset_and_json_serialization(self):
        scorer = GestureScorer()
        for i in range(10):
            scorer.add_sample(i * 0.1, i * 0.1)

        rep = scorer.evaluate()
        rep_json = rep.to_json()
        parsed = json.loads(rep_json)
        self.assertEqual(parsed['version'], 1)
        self.assertEqual(parsed['source'], 'vision.scoring')
        self.assertIn('overall_score', parsed)

        scorer.reset()
        rep_empty = scorer.evaluate()
        self.assertEqual(rep_empty.overall_score, 0)


if __name__ == '__main__':
    unittest.main()
