"""Ears' feel measures (tools/ears/feel.py) on the pitch riff with a planted problem."""
import json
import tempfile
import unittest
from pathlib import Path

try:
    from audio.takes import write_take
    from tools.ears.analyze import analyze_take
    from tools.showcase.feel_takes import render_feel_take
    from coach.session import late_ms
    from coach.runner import _hesitation_mark
except ImportError:  # minimal CI without numpy/scipy
    analyze_take = None


def report(**kw):
    audio, sr, started, _ = render_feel_take(**kw)
    with tempfile.TemporaryDirectory() as folder:
        wav = write_take(Path(folder) / "take-1.wav", audio, sr, started, source="loop")
        return json.loads(analyze_take(wav, wav.with_suffix(".json")).to_json())


@unittest.skipIf(analyze_take is None, "numpy/scipy not installed")
class EarsFeelTest(unittest.TestCase):
    def test_pitch_take_names_phrase_three(self):
        r = report()
        self.assertEqual(r["feel"], "swung")
        found = {(f["type"], f["phrase"]) for f in r["findings"] if "phrase" in f}
        self.assertEqual(found, {("straight_phrase", 3), ("uneven_attacks", 3)})
        self.assertNotIn("late", {f["type"] for f in r["findings"]})   # the groove isn't a drag
        self.assertEqual(_hesitation_mark(r)["label"], "3rd phrase · straight")
        self.assertLess(late_ms(r), 60)                                   # per beat, not per eighth

    def test_fixed_take_is_clean(self):
        r = report(straight=(), uneven=())
        self.assertEqual(r["feel"], "swung")
        self.assertEqual([f for f in r["findings"] if "phrase" in f], [])

    def test_straight_riff_is_never_told_to_swing(self):
        r = report(swing=1.0, straight=(), uneven=())
        self.assertEqual(r["feel"], "straight")
        self.assertEqual(r["findings"], [])

    def test_uneven_attacks_alone(self):
        r = report(straight=(), uneven=(2,))
        self.assertEqual({(f["type"], f["phrase"]) for f in r["findings"] if "phrase" in f}, {("uneven_attacks", 2)})


if __name__ == "__main__":
    unittest.main()
