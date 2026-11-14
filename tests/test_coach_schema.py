"""Coach feed v1 schema (protocol/coach.schema.json) and its example messages.

Fixtures only; nothing here runs an agent or a socket.
"""
import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'protocol/coach.schema.json').read_text())
Draft202012Validator.check_schema(SCHEMA)
COACH = Draft202012Validator(SCHEMA)
EXAMPLES = json.loads((ROOT / 'protocol/coach-examples.json').read_text())
RIFF_STATES = {'asleep', 'idle', 'listening', 'thinking', 'speaking', 'pointing', 'pleased'}


def frame(**kw):
    f = copy.deepcopy(EXAMPLES[2])  # the full one: drill card + pending approval
    f.update(kw)
    return f


class CoachSchemaTests(unittest.TestCase):
    def test_examples_valid(self):
        for e in EXAMPLES:
            errors = [x.message for x in COACH.iter_errors(e)]
            self.assertEqual(errors, [], e)

    def test_states_match_riff(self):
        # the dashboard's Riff (dashboard/riff.js) must know every state the feed can send
        states = set(SCHEMA['$defs']['frame']['properties']['state']['enum'])
        self.assertEqual(states, RIFF_STATES)
        riff = (ROOT / 'dashboard/riff.js').read_text()
        for s in states:
            self.assertIn(f"'{s}'", riff)

    def test_rejects_bad_messages(self):
        no_todos = frame()
        del no_todos['todos']
        bad = [
            no_todos,                                          # full snapshot: every field required
            frame(state='dancing'),
            frame(mood='angry'),
            frame(target='.loop-card'),                        # logical names, not CSS selectors
            frame(cue='x' * 241),
            frame(todos=[{'text': 'a', 'status': 'done'}]),
            frame(version=2),
            {**frame(), 'api_key': 'x'},                       # nothing extra rides along
            frame(drill_card={**EXAMPLES[2]['drill_card'], 'skill': 'Keep The Hand'}),
            frame(drill_card={**EXAMPLES[2]['drill_card'], 'rig': {'gain': 1}}),
            frame(awaiting_approval={**EXAMPLES[2]['awaiting_approval'], 'actions': [{'control': 'volume'}]}),
            frame(awaiting_approval={**EXAMPLES[2]['awaiting_approval'], 'actions': []}),
            frame(before_after={**EXAMPLES[3]['before_after'], 'worst_gap_ms': [430]}),
            frame(activity=[{'who': 'planner', 'what': 'x', 'status': 'done'}]),
            frame(activity=[{'who': 'ears', 'what': 'x', 'status': 'done'}] * 9),
            {**EXAMPLES[4], 'mime': 'audio/wav'},
            {**EXAMPLES[4], 'api_key': 'x'},                    # the TTS key never leaves the coach
            {'version': 1, 'type': 'coach.approve', 'timestamp_ms': 1},          # needs approval_id
            {'version': 1, 'type': 'coach.maybe', 'timestamp_ms': 1, 'approval_id': 'a1'},
        ]
        for b in bad:
            self.assertFalse(COACH.is_valid(b), b)


if __name__ == '__main__':
    unittest.main()
