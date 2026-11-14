import json
import sys
import unittest
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio import Engine  # noqa: E402
from engine.router import Router  # noqa: E402
from engine.runtime import Runtime  # noqa: E402

CONTROL = json.loads((ROOT / "protocol/control.schema.json").read_text())
STATE = json.loads((ROOT / "protocol/state.schema.json").read_text())
NOW = 1_800_000_000_000


def coach(seq, **kw):
    ev = dict(version=1, source="coach", seq=seq, timestamp_ms=NOW, type="action", control="loop")
    ev.update(kw)
    return ev


def drain(audio, blocks=2):
    out = np.zeros((128, 2), np.float32)
    for _ in range(blocks):
        audio.process(np.zeros(128, np.float32), out)


class CoachSourceTests(unittest.TestCase):
    def test_schema_accepts_coach_actions_and_parameters(self):
        v = Draft202012Validator(CONTROL)
        self.assertTrue(v.is_valid(coach(0)))
        self.assertTrue(v.is_valid(coach(1, type="parameter", control="filter", value=0.3, confidence=1.0)))
        self.assertFalse(v.is_valid(coach(2, source="teacher")), "other new names stay invalid")

    def test_router_routes_coach_through_the_same_gate(self):
        audio = Engine()
        router = Router(audio, clock=lambda: NOW)
        self.assertTrue(router.ingest(json.dumps(coach(0, control="bypass")).encode()))
        self.assertFalse(router.ingest(json.dumps(coach(0, control="bypass")).encode()), "duplicate dropped")
        self.assertFalse(router.ingest(json.dumps(coach(1, timestamp_ms=NOW - 5000)).encode()), "stale dropped")
        drain(audio)
        self.assertTrue(audio.snapshot()["bypass"])
        self.assertEqual(router.sources["coach"]["accepted"], 1)

    def test_state_with_a_coach_source_validates(self):
        audio = Engine()
        runtime = Runtime(audio, udp_port=None, ws_port=None)
        runtime.router.clock = lambda: NOW
        runtime.router.ingest(json.dumps(coach(0, type="parameter", control="reverb", value=0.4, confidence=0.9)).encode())
        drain(audio)
        state = runtime.snapshot()
        self.assertIn("coach", state["sources"])
        Draft202012Validator(STATE).validate(json.loads(json.dumps(state, allow_nan=False)))


if __name__ == "__main__":
    unittest.main()
