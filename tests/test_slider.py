"""Deterministic pinch/drag acceptance against the real router and DSP targets."""
import json
import math
import unittest
import numpy as np
from audio import Engine
from engine.router import Router
from vision.slider import FilterSlider
from tools.virtual_guitar.browser_vision import BrowserVision
from pathlib import Path


class SliderTests(unittest.TestCase):
    def setUp(self):
        self.audio = Engine()
        self.audio.set_filter(.4)
        self.now = 1000
        self.router = Router(self.audio, clock=lambda: self.now, monotonic=lambda: self.now)
        self.slider = FilterSlider(lambda: self.audio.snapshot()['filter']['target'])
        self.events = []
        self.drain()

    def drain(self):
        self.audio.process(np.zeros(128, np.float32), np.zeros((128, 2), np.float32))

    def step(self, y, pinch, confidence=.95):
        self.now += 100
        event = self.slider.update(y, pinch, confidence, self.now/1000, self.now)
        if event:
            self.assertTrue(self.router.ingest(json.dumps(event)))
            self.events.append(event)
        self.drain()
        return event

    def test_first_pinch_up_down_release_and_repinch(self):
        self.assertIsNone(self.step(.2, .1))  # Must first see an open hand.
        self.step(.7, .6)
        self.assertIsNone(self.step(.7, .1))  # Grab at any height, no jump.
        self.assertAlmostEqual(self.audio.snapshot()['filter']['target'], .4)
        self.step(.4, .1)
        raised = self.audio.snapshot()['filter']['target']
        self.assertGreater(raised, .4)
        self.step(.75, .1)
        lowered = self.audio.snapshot()['filter']['target']
        self.assertLess(lowered, raised)
        self.assertIsNone(self.step(.1, .6))
        self.assertAlmostEqual(self.audio.snapshot()['filter']['target'], lowered)
        self.assertIsNone(self.step(.1, .1))
        self.assertAlmostEqual(self.audio.snapshot()['filter']['target'], lowered)
        self.assertEqual([e['seq'] for e in self.events], list(range(len(self.events))))

    def test_picks_up_manual_change_between_gestures(self):
        self.step(.5, .6)
        self.step(.5, .1)
        self.step(.2, .1)
        self.step(.2, .6)
        self.audio.set_filter(.18)
        self.drain()
        self.assertIsNone(self.step(.8, .1))
        self.assertAlmostEqual(self.slider.controller.value, .18)
        self.assertAlmostEqual(self.audio.snapshot()['filter']['target'], .18)
        self.step(.6, .1)
        self.assertGreater(self.audio.snapshot()['filter']['target'], .18)

    def test_tracking_loss_confidence_and_router_stale_gate(self):
        self.step(.5, .6)
        self.step(.5, .1)
        self.step(.4, .1)
        previous = self.audio.snapshot()['filter']['target']
        self.assertIsNone(self.step(.1, .1, .2))
        self.assertIsNone(self.step(.1, .1))
        self.assertIsNone(self.step(None, None, 0))
        self.assertAlmostEqual(self.audio.snapshot()['filter']['target'], previous)
        stale = dict(self.events[-1], seq=100, timestamp_ms=self.now-1000, value=0)
        self.assertFalse(self.router.ingest(json.dumps(stale)))
        self.assertEqual(self.router.counts['stale'], 1)
        self.audio.toggle_bypass()
        self.drain()
        self.assertTrue(self.audio.snapshot()['bypass'])

    def test_bad_target_holds_and_requires_new_arm(self):
        for bad in (math.nan, -1, 2, True, None):
            slider = FilterSlider(lambda: bad)
            slider.update(.5, .6, .9, 1, 1000)
            self.assertIsNone(slider.update(.5, .1, .9, 2, 2000))
            self.assertFalse(slider.controller.armed)
            self.assertIsNotNone(slider.error)

    def test_hand_view_names_filter_and_explicit_scene_stays_optional(self):
        camera = BrowserVision(Path('/missing'), udp_port=0, hand_port=0)
        self.assertIsNone(camera.scene_name)
        self.assertEqual(camera.snapshot()['control'], 'filter')
        frame = camera._hand_frame(.5, self.slider.controller, .9, [[.5,.5]]*21, 1000)
        self.assertEqual(frame['control'], 'filter')
