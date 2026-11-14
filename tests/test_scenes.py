import json
from pathlib import Path
import unittest
from jsonschema import validate
from vision.control import Controller
from vision.scenes import SCENES, SceneMorph


class SceneTests(unittest.TestCase):
    def test_exact_endpoints_and_bounded_monotonic_blend(self):
        for preset in SCENES.values():
            m = SceneMorph(preset)
            self.assertEqual(m.values(0), preset['from'])
            for key, value in m.values(1).items():
                self.assertAlmostEqual(value, preset['to'][key])
            for i in range(101):
                self.assertTrue(all(0 <= v <= 1 for v in m.values(i / 100).values()))

    def test_controller_pair_rate_sequence_and_schema(self):
        c = Controller(rate=10, deadband=0)
        m = SceneMorph(SCENES['bloom'])
        schema = json.loads((Path(__file__).resolve().parents[1] / 'protocol/control.schema.json').read_text())
        c.update(.8, .6, .9, 0, 0)
        events = []
        for i in range(1, 101):
            gesture = c.update(.8 - .006 * i, .1, .9, i / 100, i * 10)
            if gesture:
                events.extend(m.events(gesture))
        self.assertLessEqual(len(events), 20)
        self.assertGreater(len(events), 0)
        self.assertEqual([e['seq'] for e in events], list(range(len(events))))
        for event in events:
            validate(event, schema)
        self.assertIsNone(c.update(None, None, 0, 2, 2000))

    def test_bad_preset_rejected(self):
        for value in (float('nan'), -1, True, 'loud'):
            with self.assertRaises(ValueError):
                SceneMorph(dict(name='bad', **{'from': {'filter': value, 'reverb': 0}, 'to': {'filter': 1, 'reverb': 1}}))
