import json, unittest
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'protocol/control.schema.json').read_text())
EVENTS = json.loads((ROOT / 'protocol/examples.json').read_text())

class ContractTests(unittest.TestCase):
    def test_schema_and_examples(self):
        Draft202012Validator.check_schema(SCHEMA)
        for event in EVENTS:
            Draft202012Validator(SCHEMA).validate(event)

    def test_reject_unsafe_or_ambiguous_events(self):
        validator = Draft202012Validator(SCHEMA)
        changes = [dict(value=-0.1), dict(value=1.1), dict(confidence=2), dict(confidence=-1), dict(version=2), dict(seq=-1), dict(timestamp_ms='now'), dict(source='unknown'), dict(type='action'), dict(control='loop'), dict(unexpected=True)]
        for change in changes:
            with self.subTest(change=change):
                self.assertFalse(validator.is_valid(dict(EVENTS[0], **change)))
        self.assertFalse(validator.is_valid(dict(EVENTS[1], value=0.5)))
        incomplete = dict(EVENTS[0]); incomplete.pop('confidence')
        self.assertFalse(validator.is_valid(incomplete))

if __name__ == '__main__':
    unittest.main()
