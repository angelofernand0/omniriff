import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CONTROL = Draft202012Validator(json.loads((ROOT / "protocol/control.schema.json").read_text()))
STATE = Draft202012Validator(json.loads((ROOT / "protocol/state.schema.json").read_text()))


def run_engine(*extra, timeout=60):
    return subprocess.run([sys.executable, "-m", "engine", "--headless", "--no-keyboard",
                           "--ws-port", "0", "--udp-port", "0", *extra],
                          cwd=ROOT, capture_output=True, text=True, timeout=timeout)


class SessionLogTests(unittest.TestCase):
    def test_replay_session_is_logged_with_valid_controls_and_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "runs" / "session.jsonl"
            r = run_engine("--replay", "engine/demo-controls.jsonl", "--duration", "4", "--session-log", str(log))
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            records = [json.loads(line) for line in log.read_text().splitlines()]
            kinds = [x["kind"] for x in records]
            self.assertEqual(kinds[0], "start")
            self.assertEqual(kinds[-1], "stop")
            controls = [x["event"] for x in records if x["kind"] == "control"]
            states = [x["state"] for x in records if x["kind"] == "state"]
            self.assertGreaterEqual(len(controls), 3, "the demo script's early controls are logged")
            self.assertGreaterEqual(len(states), 6, "about 2 Hz over 4 s, plus a final one")
            for ev in controls:
                CONTROL.validate(ev)
            for st in states:
                STATE.validate(st)
            self.assertTrue(all(isinstance(x["t"], int) for x in records))

    def test_refuses_to_overwrite_an_existing_log(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl") as f:
            r = run_engine("--duration", "1", "--session-log", f.name)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("refusing to overwrite", r.stderr)


if __name__ == "__main__":
    unittest.main()
