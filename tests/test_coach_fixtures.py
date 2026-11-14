"""Planted coach mistakes must be visible to the real local analyzers."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from coach.fixtures.generate import START_UNIX_MS, generate
from tools.ears.analyze import analyze_take
from vision.eyes import HandMovementAnalyzer


def analyze_hand_log(path: Path):
    """Feed the fixture's R17-shaped wrist samples to current Eyes logic."""
    analyzer = HandMovementAnalyzer()
    with path.open() as stream:
        for line in stream:
            sample = json.loads(line)
            hand = sample["hands"][0]
            x, y = hand["wrist"]
            analyzer.add_sample((sample["timestamp_ms"] - START_UNIX_MS) / 1000, x, y)
    return analyzer.analyze()


class CoachFixtureTests(unittest.TestCase):
    def test_planted_chord_change_delays_and_matching_hand_freezes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = generate(root)
            self.assertEqual(manifest["source"], "synthetic_fixture")
            rows = {row["take_id"]: row for row in manifest["takes"]}
            self.assertEqual(set(rows), {"coach-before", "coach-clean", "coach-after"})

            reports = {}
            for name, row in rows.items():
                sidecar = json.loads((root / row["sidecar"]).read_text())
                self.assertEqual(sidecar["source"], "synthetic_fixture")
                self.assertEqual(sidecar["take_id"], name)
                self.assertEqual(sidecar["started_unix_ms"], START_UNIX_MS)
                ear = analyze_take(root / row["wav"], root / row["sidecar"])
                eye = analyze_hand_log(root / row["hand_log"])
                self.assertEqual(ear.take_id, name)
                self.assertEqual(ear.strum_count, 16)
                self.assertGreater(eye.sample_count, 200)
                reports[name] = (ear, eye)

            before, before_eye = reports["coach-before"]
            hesitations = [item for item in before.findings if item["type"] == "hesitation"]
            self.assertEqual(len(hesitations), 3)
            self.assertEqual(len(before_eye.stalls), 3)
            for finding, onset_ms, stall, planted in zip(
                hesitations, rows["coach-before"]["planted_onsets_ms"],
                before_eye.stalls, rows["coach-before"]["planted_stalls_ms"],
            ):
                self.assertAlmostEqual(finding["at_ms"], onset_ms, delta=40)
                self.assertAlmostEqual(finding["extra_ms"], 400, delta=50)
                self.assertAlmostEqual(stall["start_time_s"] * 1000, planted[0], delta=40)
                self.assertGreaterEqual(stall["duration_ms"], 300)

            clean, clean_eye = reports["coach-clean"]
            self.assertFalse([item for item in clean.findings if item["type"] == "hesitation"])
            self.assertEqual(clean_eye.stalls, [])

            after, after_eye = reports["coach-after"]
            self.assertFalse([item for item in after.findings if item["type"] == "hesitation"])
            self.assertEqual(after_eye.stalls, [])  # 120 ms is below Eyes' stall threshold
            late = [item for item in after.findings if item["type"] == "late"]
            self.assertEqual(len(late), 3)
            for finding, onset_ms in zip(late, rows["coach-after"]["planted_onsets_ms"]):
                self.assertAlmostEqual(finding["at_ms"], onset_ms, delta=40)
                self.assertAlmostEqual(finding["extra_ms"], 120, delta=40)


if __name__ == "__main__":
    unittest.main()
