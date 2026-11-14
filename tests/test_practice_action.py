"""R24: the practice action is a request for the coach, never an audio change."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio import Engine  # noqa: E402
from engine.runtime import Runtime  # noqa: E402

CONTROL = Draft202012Validator(json.loads((ROOT / "protocol/control.schema.json").read_text()))
STATE = Draft202012Validator(json.loads((ROOT / "protocol/state.schema.json").read_text()))
NOW = 1_800_000_000_000


def ev(seq, source="arduino", control="practice", **kw):
    e = dict(version=1, source=source, seq=seq, timestamp_ms=NOW, type="action", control=control)
    e.update(kw)
    return e


def drain(audio, blocks=2):
    out = np.zeros((128, 2), np.float32)
    for _ in range(blocks):
        audio.process(np.zeros(128, np.float32), out)


class PracticeSchemaTests(unittest.TestCase):
    def test_practice_is_an_action_from_player_inputs_only(self):
        for source in ("arduino", "dashboard", "manual"):
            self.assertTrue(CONTROL.is_valid(ev(0, source)), source)
        for source in ("vision", "coach", "sensecap"):
            self.assertFalse(CONTROL.is_valid(ev(0, source)), f"{source} must not start a session")
        self.assertFalse(CONTROL.is_valid(ev(0, value=1.0)))
        self.assertFalse(CONTROL.is_valid(ev(0, type="parameter", value=1.0, confidence=1.0)))

    def test_existing_controls_unchanged(self):
        self.assertTrue(CONTROL.is_valid(ev(0, control="loop")))
        self.assertTrue(CONTROL.is_valid(ev(0, source="vision", type="parameter", control="filter",
                                            value=0.5, confidence=0.9)))


class PracticeRoutingTests(unittest.TestCase):
    def setUp(self):
        self.audio = Engine()
        self.runtime = Runtime(self.audio, udp_port=None, ws_port=None)
        self.router = self.runtime.router
        self.router.clock = lambda: NOW

    def test_practice_never_touches_audio_and_is_counted_in_state(self):
        before = self.audio.snapshot()
        self.assertNotIn("pedal", self.runtime.snapshot(), "omitted until the first request")
        self.assertTrue(self.router.ingest(json.dumps(ev(0)).encode()))
        drain(self.audio)
        after = self.audio.snapshot()
        for key in ("loop", "bypass", "filter", "reverb"):
            self.assertEqual(before[key], after[key], key)
        state = self.runtime.snapshot()
        self.assertEqual(state["pedal"], {"practice_count": 1, "last_practice_ms": NOW})
        STATE.validate(json.loads(json.dumps(state, allow_nan=False)))

    def test_same_gate_as_every_other_control(self):
        self.assertTrue(self.router.ingest(json.dumps(ev(0)).encode()))
        self.assertFalse(self.router.ingest(json.dumps(ev(0)).encode()), "duplicate dropped")
        self.assertFalse(self.router.ingest(json.dumps(ev(1, timestamp_ms=NOW - 5000)).encode()), "stale dropped")
        self.assertFalse(self.router.ingest(json.dumps(ev(2, source="vision")).encode()), "vision rejected")
        self.assertEqual(self.router.pedal["practice_count"], 1)
        self.assertTrue(self.router.ingest(json.dumps(ev(3, source="dashboard")).encode()))
        self.assertEqual(self.router.pedal["practice_count"], 2)
        self.assertEqual(self.router.sources["arduino"]["accepted"], 1)

    def test_loop_still_toggles_after_practice(self):
        self.router.ingest(json.dumps(ev(0)).encode())
        self.router.ingest(json.dumps(ev(1, control="loop")).encode())
        drain(self.audio)
        self.assertNotEqual(self.audio.snapshot()["loop"], Engine().snapshot()["loop"])


if __name__ == "__main__":
    unittest.main()
