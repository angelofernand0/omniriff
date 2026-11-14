import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from audio import Engine
from engine.router import Router
from engine.replay import Replay
from vision.control import Controller
from vision.scenes import SCENES
from vision.setlist import Setlist, main


class SetlistTests(unittest.TestCase):
    def bank(self):
        return Setlist({'scenes': list(SCENES.values())})

    def test_switch_requires_open_hand_and_keeps_sequence_through_router(self):
        bank = self.bank()
        controller = Controller(rate=10)
        audio = Engine()
        clock = [0]
        router = Router(audio, clock=lambda: clock[0], monotonic=lambda: clock[0])
        events = []
        for index in (0, 1, 0, 1):
            if bank.select(index):
                controller.rearm()
            clock[0] += 200
            # A held pinch after switching cannot activate the next scene.
            self.assertIsNone(controller.update(.2, .1, .9, clock[0]/1000, clock[0]))
            clock[0] += 100
            self.assertIsNone(controller.update(.2, .6, .9, clock[0]/1000, clock[0]))
            clock[0] += 100
            gesture = controller.update(.2, .1, .9, clock[0]/1000, clock[0])
            self.assertIsNotNone(gesture)  # Same amount still emits in the new scene.
            pair = bank.current.events(gesture)
            for event in pair:
                self.assertTrue(router.ingest(json.dumps(event)))
            events.extend(pair)
            audio.process(np.zeros(128, np.float32), np.zeros((128, 2), np.float32))
            state = audio.snapshot()
            self.assertAlmostEqual(state['filter']['target'], bank.current.end['filter'])
            self.assertAlmostEqual(state['reverb']['target'], bank.current.end['reverb'])
        self.assertEqual([event['seq'] for event in events], list(range(8)))
        self.assertEqual(router.counts['duplicate'], 0)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'show.jsonl'
            path.write_text(''.join(json.dumps(event)+'\n' for event in events))
            self.assertEqual(len(Replay.load(path).entries), 8)

    def test_next_previous_wrap_and_unavailable_keys(self):
        bank = self.bank()
        self.assertFalse(bank.key(ord('1')))
        self.assertFalse(bank.key(ord('9')))
        self.assertFalse(bank.key(ord('q')))
        self.assertTrue(bank.key(ord('p')))
        self.assertEqual(bank.index, 1)
        self.assertTrue(bank.key(ord('n')))
        self.assertEqual(bank.index, 0)
        self.assertTrue(bank.key(ord('2')))
        single = Setlist({'scenes': [SCENES['bloom']]})
        self.assertFalse(single.key(ord('n')))
        with self.assertRaises(ValueError):
            bank.select(-1)

    def test_entire_file_validated_before_use(self):
        bad = copy.deepcopy(SCENES['rise'])
        bad['to']['filter'] = 2
        for data in ({}, [], {'scenes': []}, {'scenes': [SCENES['bloom']]*10},
                     {'scenes': [SCENES['bloom'], bad]}, {'scenes': [], 'extra': True}):
            with self.assertRaises(ValueError):
                Setlist(data)
        demo = Path(__file__).parents[1]/'vision/setlist-demo.json'
        self.assertEqual(len(Setlist(json.loads(demo.read_text())).scenes), 3)

    def test_rearm_preserves_rate_limit(self):
        controller = Controller(rate=10)
        controller.update(.5, .6, .9, 0, 0)
        self.assertIsNotNone(controller.update(.5, .1, .9, .1, 100))
        controller.rearm()
        controller.update(.5, .6, .9, .11, 110)
        self.assertIsNone(controller.update(.5, .1, .9, .12, 120))
        event = controller.update(.5, .1, .9, .21, 210)
        self.assertEqual(event['seq'], 1)

    def test_builder_preserves_order_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            custom = copy.deepcopy(SCENES['bloom'])
            custom['name'] = 'My fitted tone'
            (root/'custom.json').write_text(json.dumps(custom))
            args = ['rise', str(root/'custom.json'), 'bloom', '--output', str(root/'show.json')]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                main(args)
                before = (root/'show.json').read_text()
                with self.assertRaises(SystemExit) as error:
                    main(args)
                self.assertEqual(error.exception.code, 2)
            self.assertEqual(before, (root/'show.json').read_text())
            bank = Setlist(json.loads(before))
            self.assertEqual([scene.name for scene in bank.scenes], ['Underwater to Spotlight', 'My fitted tone', 'Clear to Cosmos'])
