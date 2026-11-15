"""tools/promo/scenes: page building and frame timing (no browser needed)."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.promo.scenes import record  # noqa: E402


class SceneTests(unittest.TestCase):
    def test_page_inlines_brand_assets_and_fonts(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = record.build_page(Path(tmp)).read_text(encoding="utf-8")
        self.assertNotIn("{{", html, "every placeholder is filled")
        self.assertIn("Silkscreen-400.woff2", html)
        self.assertIn('aria-label="OmniRiff"', html, "the mascot and wordmark come from dashboard/brand")

    def test_scene_durations_match_the_edit_plan(self):
        # The EDL's motion segments must have a matching scene of the same length.
        import json
        edl = json.loads((ROOT / "docs/video/edl.json").read_text())
        src = (ROOT / "tools/promo/scenes/scenes.html").read_text(encoding="utf-8")
        durations = {name: float(d) for name, d in re.findall(r"^  (\w+): \{ duration: ([\d.]+)", src, re.M)}
        aliases = {"end": "end"}
        for seg in edl["segments"]:
            if seg.get("kind") != "motion":
                continue
            scene = aliases.get(seg["scene"], seg["scene"])
            self.assertIn(scene, durations, f"EDL needs scene {scene!r}")
            self.assertAlmostEqual(durations[scene], seg["end_s"] - seg["start_s"], places=3, msg=scene)

    def test_frame_times_are_exact(self):
        times = record.frame_times(3.0)
        self.assertEqual(len(times), 90)
        self.assertEqual(times[0], 0.0)
        self.assertAlmostEqual(times[-1], 89 / 30)

    def test_no_wall_clock_or_randomness_in_scenes(self):
        # Determinism: every render of a scene must be identical.
        src = (ROOT / "tools/promo/scenes/scenes.html").read_text(encoding="utf-8")
        for banned in ("Math.random", "Date.now", "performance.now", "requestAnimationFrame"):
            self.assertNotIn(banned, src, banned)


if __name__ == "__main__":
    unittest.main()
