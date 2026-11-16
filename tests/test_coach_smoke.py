"""The coach harness remains inspectable without network or API credentials."""
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path


class CoachSmokeTests(unittest.TestCase):
    @unittest.skipUnless(find_spec("deepagents"), "coach/requirements.txt is optional in core CI")
    def test_harness_tools_and_virtual_workspace_files(self):
        from coach.smoke import EXPECTED, MARKER, make_agent, make_workspace, tool_names

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            make_workspace(root)
            self.assertEqual(EXPECTED - tool_names(make_agent(root, offline=True)), set())
            self.assertTrue((root / "skills" / "smoke-read" / "SKILL.md").is_file())
            self.assertIn(MARKER, (root / "memories" / "player.md").read_text())


if __name__ == "__main__":
    unittest.main()
