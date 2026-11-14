import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio.fileio import write_wav  # noqa: E402
from tools.ears import analyze_take, analyze_timing, detect_onsets  # noqa: E402
from tools.virtual_guitar.guitar import _add_strum, _pickup_and_body  # noqa: E402

SR = 48000


def strums(times, seed=1, sustain=1.2):
    """Synthetic (labeled) guitar strums at known times, via the virtual guitar's string model."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int((max(times) + 1.5) * SR))
    for i, t in enumerate(times):
        _add_strum(out, t, (0, 2, 2, 1, 0, 0), SR, rng, velocity=0.8 if i % 2 == 0 else 0.45,
                   direction="down" if i % 2 == 0 else "up", sustain=sustain)
    out = _pickup_and_body(out, SR)
    return (out / np.max(np.abs(out)) * 0.5).astype(np.float32)


class OnsetTests(unittest.TestCase):
    def test_finds_every_strum_within_fifteen_ms(self):
        times = [0.4 + 0.28 * i for i in range(12)]
        onsets = detect_onsets(strums(times), SR)
        self.assertEqual(len(onsets), len(times))
        self.assertLessEqual(max(min(abs(o - t * 1000) for o in onsets) for t in times), 15.0)

    def test_silence_and_hum_have_no_onsets(self):
        t = np.arange(2 * SR) / SR
        self.assertEqual(len(detect_onsets(np.zeros(2 * SR, np.float32), SR)), 0)
        self.assertEqual(len(detect_onsets((0.01 * np.sin(2 * np.pi * 60 * t)).astype(np.float32), SR)), 0)

    def test_sustained_chord_beating_is_not_a_strum(self):
        from audio.fileio import make_test_signal  # sawtooth chord restruck once per second
        chord = make_test_signal(4.2, SR)[int(0.2 * SR):]  # starts mid-chord, like a loop take
        chord[:240] *= np.linspace(0, 1, 240, dtype=np.float32)  # the take's 5 ms seam fade-in
        onsets = detect_onsets(chord, SR)
        self.assertEqual(len(onsets), 4)
        for got, want in zip(onsets, [800, 1800, 2800, 3800]):
            self.assertAlmostEqual(got, want, delta=15)


class TimingTests(unittest.TestCase):
    def test_hesitation_at_a_chord_change_is_found(self):
        times = [0.5 + 0.3 * i for i in range(8)] + [0.5 + 0.3 * 7 + 0.75 + 0.3 * i for i in range(6)]
        _, _, median, stability, findings = analyze_timing(detect_onsets(strums(times), SR))
        hes = [f for f in findings if f["type"] == "hesitation"]
        self.assertEqual(len(hes), 1)
        self.assertAlmostEqual(hes[0]["at_ms"], times[8] * 1000, delta=15)
        self.assertAlmostEqual(hes[0]["extra_ms"], 450, delta=20)
        self.assertEqual(hes[0]["severity"], "severe")
        self.assertAlmostEqual(median, 300, delta=10)
        self.assertGreater(stability, 0.9)

    def test_rush_and_drag_are_flagged(self):
        onsets = [0, 300, 600, 900, 1100, 1400, 1700, 2000, 2380, 2680, 2980]  # 1100 early, 2380 late
        _, _, _, _, findings = analyze_timing(onsets)
        kinds = {(f["type"], f["at_ms"]) for f in findings}
        self.assertIn(("early", 1100.0), kinds)
        self.assertIn(("late", 2380.0), kinds)

    def test_steady_playing_has_no_findings(self):
        self.assertEqual(analyze_timing([i * 250 for i in range(12)])[4], [])


class TakeReportTests(unittest.TestCase):
    def test_report_from_a_captured_take_passes_sidecar_fields_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "take-x-1.wav"
            write_wav(wav, strums([0.3 + 0.3 * i for i in range(10)]), SR)
            wav.with_suffix(".json").write_text(json.dumps({"take_id": "take-x-1", "started_unix_ms": 1234}))
            report = analyze_take(wav)
            data = json.loads(report.to_json())
            self.assertEqual(data["take_id"], "take-x-1")
            self.assertEqual(data["started_unix_ms"], 1234)
            self.assertEqual(data["strum_count"], 10)
            self.assertIn("strums", data["summary"])

    def test_silent_or_sparse_take_is_not_judgeable(self):
        with tempfile.TemporaryDirectory() as tmp:
            silent = Path(tmp) / "silent.wav"
            write_wav(silent, np.zeros(3 * SR, np.float32), SR)
            r = json.loads(analyze_take(silent).to_json())
            self.assertFalse(r["judgeable"])
            self.assertEqual((r["strum_count"], r["findings"], r["min_strums"]), (0, [], 4))
            sparse = Path(tmp) / "sparse.wav"
            write_wav(sparse, strums([0.3, 0.9, 1.5]), SR)
            self.assertFalse(json.loads(analyze_take(sparse).to_json())["judgeable"])
            full = Path(tmp) / "full.wav"
            write_wav(full, strums([0.3 + 0.3 * i for i in range(8)]), SR)
            self.assertTrue(json.loads(analyze_take(full).to_json())["judgeable"])

    def test_cli_refuses_to_overwrite(self):
        from tools.ears.__main__ import main
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "t.wav"
            write_wav(wav, strums([0.3, 0.6, 0.9, 1.2]), SR)
            out = Path(tmp) / "r.json"
            out.write_text("{}")
            with self.assertRaises(SystemExit):
                main([str(wav), "--output", str(out)])


if __name__ == "__main__":
    unittest.main()
