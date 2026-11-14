"""Drill skills are discoverable and keep approval/evidence boundaries visible."""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "coach" / "workspace" / "skills"
EXPECTED = {"isolate-the-change", "slow-then-speed-up", "dry-check", "keep-the-hand-moving"}


class CoachSkillTests(unittest.TestCase):
    def test_four_drills_have_discoverable_frontmatter(self):
        self.assertEqual({p.name for p in ROOT.iterdir() if p.is_dir()}, EXPECTED)
        for name in EXPECTED:
            text = (ROOT / name / "SKILL.md").read_text()
            self.assertTrue(text.startswith("---\n"), name)
            frontmatter = text.split("---", 2)[1]
            self.assertRegex(frontmatter, rf"(?m)^name: {re.escape(name)}$")
            match = re.search(r"(?m)^description: (.+)$", frontmatter)
            self.assertIsNotNone(match, name)
            self.assertLess(len(match.group(1)), 1024)
            self.assertIn("rig_control", text)
            self.assertIn("Pass when", text)


if __name__ == "__main__":
    unittest.main()
