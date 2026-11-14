"""The coach harness remains inspectable without network or API credentials."""
import tempfile
import unittest
from pathlib import Path

from coach.smoke import EXPECTED, MARKER, make_agent, make_workspace, tool_names


class CoachSmokeTests(unittest.TestCase):
    def test_harness_tools_and_virtual_workspace_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            make_workspace(root)
            self.assertEqual(EXPECTED - tool_names(make_agent(root)), set())
            self.assertTrue((root / "skills" / "smoke-read" / "SKILL.md").is_file())
            self.assertIn(MARKER, (root / "memories" / "player.md").read_text())


if __name__ == "__main__":
    unittest.main()
