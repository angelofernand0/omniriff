"""Tests for biomechanical hand movement & pendulum strum analyzer (Coach Eyes - Piece C)."""
import json
import unittest

from vision.eyes import (
    HandMovementAnalyzer,
    HandReport,
    StallEvent,
    generate_synthetic_strum_take,
)


class EyesAnalyzerTests(unittest.TestCase):
    def test_insufficient_samples_fails_gracefully(self):
        analyzer = HandMovementAnalyzer()
        report = analyzer.analyze()
        self.assertEqual(report.sample_count, 0)
        self.assertIn("Insufficient", report.summary)

        analyzer.add_sample(0.0, 0.5, 0.5)
        analyzer.add_sample(0.05, 0.5, 0.5)
        report2 = analyzer.analyze()
        self.assertEqual(report2.sample_count, 2)
        self.assertIn("Insufficient", report2.summary)

    def test_rejects_nonfinite_and_out_of_order_timestamps(self):
        analyzer = HandMovementAnalyzer()
        analyzer.add_sample(0.0, 0.5, 0.5)
        analyzer.add_sample(0.1, 0.5, 0.5)
        analyzer.add_sample(0.2, float('nan'), 0.5)  # nan rejected
        analyzer.add_sample(0.2, 0.5, float('inf'))  # inf rejected
        analyzer.add_sample(0.05, 0.5, 0.5)          # Backward in time (0.05 <= 0.1) rejected
        self.assertEqual(len(analyzer.samples), 2)

    def test_steady_strumming_has_zero_stalls_and_accurate_tempo(self):
        # 120 BPM steady strumming for 8 seconds, zero stalls
        samples = generate_synthetic_strum_take(
            duration_s=8.0, fps=30.0, tempo_bpm=120.0, stall_start_s=None
        )
        analyzer = HandMovementAnalyzer()
        for t, x, y in samples:
            analyzer.add_sample(t, x, y)
        report = analyzer.analyze()

        self.assertEqual(len(report.stalls), 0)
        self.assertEqual(report.motion_continuity_score, 1.0)
        self.assertIsNotNone(report.tempo_bpm)
        self.assertAlmostEqual(report.tempo_bpm, 120.0, delta=5.0)
        self.assertGreaterEqual(report.tempo_stability, 0.75)
        self.assertIn("Zero stalls", report.summary)

    def test_detects_exact_chord_change_stall(self):
        # 6 seconds of playing at 120 BPM with a 400ms stall at t=2.5s
        samples = generate_synthetic_strum_take(
            duration_s=6.0, fps=40.0, tempo_bpm=120.0, stall_start_s=2.5, stall_duration_s=0.40
        )
        analyzer = HandMovementAnalyzer(min_stall_duration_s=0.20)
        for t, x, y in samples:
            analyzer.add_sample(t, x, y)
        report = analyzer.analyze()

        self.assertEqual(len(report.stalls), 1)
        stall = report.stalls[0]
        # Stall should be detected at t=2.5s within 35ms
        self.assertAlmostEqual(stall['start_time_s'], 2.5, delta=0.035)
        self.assertAlmostEqual(stall['duration_ms'], 400, delta=40)
        self.assertEqual(stall['severity'], 'moderate')
        self.assertIn(f"{stall['duration_ms']} ms", stall['message'])
        self.assertIn("Cause: hand stops swinging", report.summary)
        self.assertLess(report.motion_continuity_score, 1.0)

    def test_json_export_and_report_contract(self):
        samples = generate_synthetic_strum_take(duration_s=3.0, fps=20.0, tempo_bpm=120.0)
        analyzer = HandMovementAnalyzer()
        for t, x, y in samples:
            analyzer.add_sample(t, x, y)
        report = analyzer.analyze()

        raw_json = report.to_json()
        parsed = json.loads(raw_json)
        self.assertEqual(parsed['version'], 1)
        self.assertEqual(parsed['source'], 'vision.eyes')
        self.assertIn('duration_s', parsed)
        self.assertIn('sample_count', parsed)
        self.assertIn('strum_count', parsed)
        self.assertIn('motion_continuity_score', parsed)
        self.assertIn('stalls', parsed)
        self.assertIn('summary', parsed)

    def test_multiple_stalls_classified_by_severity(self):
        analyzer = HandMovementAnalyzer(min_stall_duration_s=0.18)
        # 1. 200 ms stall (minor)
        analyzer.add_sample(0.0, 0.4, 0.5)
        analyzer.add_sample(0.2, 0.4, 0.5)
        # 2. Moving
        analyzer.add_sample(0.3, 0.4, 0.8)
        # 3. 500 ms stall (severe)
        analyzer.add_sample(0.4, 0.4, 0.2)
        analyzer.add_sample(0.9, 0.4, 0.2)
        # 4. Moving
        analyzer.add_sample(1.0, 0.4, 0.7)

        report = analyzer.analyze()
        self.assertEqual(len(report.stalls), 2)
        self.assertEqual(report.stalls[0]['severity'], 'minor')
        self.assertEqual(report.stalls[1]['severity'], 'severe')
