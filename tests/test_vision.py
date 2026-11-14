import unittest
from vision.control import Controller


class GestureTests(unittest.TestCase):
    def test_requires_open_then_pinch_and_rearms_after_loss(self):
        c = Controller()
        self.assertIsNone(c.update(.5, .1, .9, 0, 0))
        c.update(.5, .6, .9, .1, 100)
        self.assertIsNotNone(c.update(.5, .1, .9, .2, 200))
        self.assertIsNone(c.update(None, None, 0, .3, 300))
        self.assertIsNone(c.update(.3, .1, .9, .4, 400))

    def test_gate_rate_deadband_and_smoothing(self):
        c = Controller()
        c.update(.8, .6, .9, 0, 0)
        first = c.update(.8, .1, .9, .1, 100)
        self.assertEqual(first['value'], 0)
        self.assertIsNone(c.update(.2, .1, .9, .11, 110))
        next_event = c.update(.2, .1, .9, .2, 200)
        self.assertTrue(0 < next_event['value'] < 1)
        self.assertIsNone(c.update(.2, .1, .2, .3, 300))
        stable = Controller()
        stable.update(.5, .6, .9, 0, 0)
        stable.update(.5, .1, .9, .1, 100)
        self.assertIsNone(stable.update(.50001, .1, .9, .2, 200))

    def test_calibration_invalid(self):
        for kwargs in ({'low': .1, 'high': .9}, {'rate': 0}, {'tau': 0}, {'low': float('nan')}):
            with self.assertRaises(ValueError):
                Controller(**kwargs)

    def test_events_match_shared_schema(self):
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator
        validator = Draft202012Validator(json.loads((Path(__file__).resolve().parents[1] / 'protocol/control.schema.json').read_text()))
        c = Controller()
        c.update(.8, .6, .9, 0, 0)
        count = 0
        for i in range(1, 101):
            event = c.update(.8 - i * .006, .1, .9, i / 100, i * 10)
            if event:
                validator.validate(event)
                count += 1
        self.assertGreater(count, 0)
        self.assertLessEqual(count, 20)
