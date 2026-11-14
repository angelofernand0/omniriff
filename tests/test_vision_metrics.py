import unittest
from vision.metrics import FrameMetrics


class MetricsTests(unittest.TestCase):
    def test_rate_includes_interframe_wait_and_samples_are_bounded(self):
        metrics = FrameMetrics(2)
        metrics.record(0, .01, 0)
        metrics.record(.1, .12, 1)
        metrics.record(.2, .23, 2)
        result = metrics.snapshot()
        self.assertAlmostEqual(result['processed_fps'], 3/.23)
        self.assertAlmostEqual(result['processing_mean_ms'], 20)
        self.assertEqual(result['percentile_window_frames'], 2)
        self.assertAlmostEqual(result['processing_p95_ms'], 30)
        self.assertEqual(result['events'], 3)

    def test_no_measurement_is_not_zero_latency(self):
        self.assertIsNone(FrameMetrics().snapshot()['processing_p95_ms'])
        for start, end, events in ((2, 1, 0), (0, float('nan'), 0), (0, 1, -1)):
            with self.assertRaises(ValueError):
                FrameMetrics().record(start, end, events)
