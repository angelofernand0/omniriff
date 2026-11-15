"""vision/technique.py finds planted fretting/picking causes in synthetic two-hand tracks."""
import json
import tempfile
import unittest
from pathlib import Path

try:
    from tools.showcase.hands import Faults, render
    from audio.takes import write_take
    from tools.ears.analyze import analyze_take
    from vision.technique import analyze
except ImportError:  # minimal CI without numpy/scipy
    analyze = None


def run(faults):
    audio, sr, started, records, _ = render(faults)
    with tempfile.TemporaryDirectory() as folder:
        wav = write_take(Path(folder) / "take-1.wav", audio, sr, started, source="loop")
        ear = json.loads(analyze_take(wav, wav.with_suffix(".json")).to_json())
    return analyze(records, ear, "take-1")


@unittest.skipIf(analyze is None, "numpy/scipy not installed")
class TechniqueTest(unittest.TestCase):
    def test_clean_playing_has_no_findings(self):
        report = run(Faults())
        self.assertTrue(report.available)
        self.assertEqual(len(report.changes), 3)
        self.assertEqual(report.findings, [])

    def test_late_ring_finger_is_named_with_its_lag(self):
        report = run(Faults(late_finger="ring", lag_s=0.28))
        self.assertEqual(report.findings[0]["type"], "pattern")
        self.assertEqual(report.findings[0]["finger"], "ring")
        late = [f for f in report.findings if f["type"] == "late_finger"]
        self.assertEqual(len(late), 3)
        for finding in late:
            self.assertEqual(finding["finger"], "ring")
            self.assertTrue(180 <= finding["lag_ms"] <= 320, finding)
        self.assertIn("ring finger", report.summary)

    def test_late_start_is_not_blamed_on_a_finger(self):
        report = run(Faults(start_delay_s=0.25))
        types = {f["type"] for f in report.findings}
        self.assertIn("late_start", types)
        self.assertNotIn("late_finger", types)

    def test_picking_hand_is_found_by_motion_not_label(self):
        report = run(Faults())
        self.assertEqual(report.picking["hand"], "Left")  # mirrored label; it is the swinging hand
        self.assertGreater(report.picking["stroke_size_hands"], 0.5)

    def test_wrist_only_log_is_unavailable_not_guessed(self):
        records = [{"timestamp_ms": 1000 + 33 * i, "hands": [{"handedness": "Right", "wrist": [0.5, 0.5],
                                                               "confidence": 0.9}]} for i in range(60)]
        report = analyze(records, None, "old")
        self.assertFalse(report.available)
        self.assertEqual(report.findings, [])

    def test_one_hand_in_view_says_to_frame_the_neck(self):
        audio, sr, started, records, _ = render(Faults(late_finger="ring", lag_s=0.28))
        picking_only = [{**r, "hands": [h for h in r["hands"] if h["handedness"] == "Left"]} for r in records]
        report = analyze(picking_only, None, "one")
        self.assertIn("fretting hand", report.reason)
        self.assertEqual(report.changes, [])


if __name__ == "__main__":
    unittest.main()
