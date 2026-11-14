"""Hand-view v1 schema, the simulated hand feed, and the dashboard's hand panel assets.

The feed is display-only and simulated here; nothing below measures vision accuracy.
"""
import asyncio
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.sim.hand import HandState, hand_points, pinch_ratio, serve_hand

ROOT = Path(__file__).resolve().parents[1]
HAND = Draft202012Validator(json.loads((ROOT / 'protocol/hand.schema.json').read_text()))
Draft202012Validator.check_schema(HAND.schema)


def frame(**kw):
    base = dict(version=1, type='hand', timestamp_ms=1, present=True, engaged=False,
                confidence=0.9, control='filter', value=0.5, landmarks=hand_points(0.5, 0.6, 0.0))
    base.update(kw)
    return base


class HandSchemaTests(unittest.TestCase):
    def test_accepts_vision_shapes(self):
        # the shapes vision/ publishes (PR #13): no hand, tracked hand, engaged, Scene Morph
        self.assertTrue(HAND.is_valid(frame(present=False, confidence=0, value=None, landmarks=[])))
        self.assertTrue(HAND.is_valid(frame()))
        self.assertTrue(HAND.is_valid(frame(engaged=True, value=0.8)))
        self.assertTrue(HAND.is_valid(frame(control=None, value=0.3)))
        self.assertTrue(HAND.is_valid(frame(control='reverb', value=None)))

    def test_rejects_bad_frames(self):
        bad = [
            frame(landmarks=[]),                                   # present needs 21 points
            frame(landmarks=hand_points(0.5, 0.6, 0)[:20]),
            frame(present=False, landmarks=hand_points(0.5, 0.6, 0)),  # absent must be empty
            frame(landmarks=[[1.2, 0.5]] * 21),                    # outside the image
            frame(landmarks=[[0.5, 0.5, 0.1]] * 21),               # x, y only
            frame(control='loop'),
            frame(value=1.5),
            frame(confidence=-0.1),
            frame(version=2),
            frame(type='state'),
            {**frame(), 'pixels': 'x'},                            # never camera data
        ]
        for f in bad:
            self.assertFalse(HAND.is_valid(f), f)


class FakeHandTests(unittest.TestCase):
    def test_pinch_geometry_crosses_vision_thresholds(self):
        # vision engages below 0.25 and releases above 0.45 (thumb-index / palm width)
        for wob in (0.0, 1.0, 2.5, 4.0):
            self.assertGreater(pinch_ratio(hand_points(0.5, 0.6, 0.0, wob)), 0.45)
            self.assertLess(pinch_ratio(hand_points(0.5, 0.6, 1.0, wob)), 0.25)

    def test_state_frames_are_valid_and_follow_the_value(self):
        s = HandState()
        self.assertTrue(HAND.is_valid(s.frame(10.0)))
        self.assertEqual(s.frame(10.0)['landmarks'], [])
        s.present = True
        self.assertTrue(HAND.is_valid(s.frame(10.0)))
        s.engaged, s.control = True, 'reverb'
        s.value = 0.0; low = s.frame(10.0)
        s.value = 1.0; high = s.frame(10.0)
        self.assertTrue(HAND.is_valid(low) and HAND.is_valid(high))
        self.assertLess(high['landmarks'][0][1], low['landmarks'][0][1])  # higher value, wrist higher in frame
        self.assertTrue(high['engaged'])

    def test_feed_serves_valid_frames(self):
        from websockets.asyncio.client import connect

        async def go():
            s = HandState(); s.present = True
            port = asyncio.get_running_loop().create_future()
            task = asyncio.create_task(serve_hand(s, 0, rate_hz=50, ready=port.set_result))
            try:
                p = await asyncio.wait_for(port, 2)
                async with connect(f'ws://127.0.0.1:{p}') as ws:
                    frames = [json.loads(await asyncio.wait_for(ws.recv(), 1)) for _ in range(3)]
            finally:
                task.cancel()
            return frames

        for f in asyncio.run(go()):
            self.assertTrue(HAND.is_valid(f), f)
            self.assertEqual(len(f['landmarks']), 21)


class DashboardHandAssetsTests(unittest.TestCase):
    def test_panel_and_safety_rules_present(self):
        html = (ROOT / 'dashboard/index.html').read_text()
        js = (ROOT / 'dashboard/app.js').read_text()
        self.assertIn('id="handCanvas"', html)
        self.assertIn('47802', js)
        self.assertIn('HAND_STALE_MS', js)          # aged by receive time
        self.assertIn('hand.frame = null', js)      # cleared on stale/disconnect
        self.assertNotIn("'ARMED'", js.upper())   # present != armed: no such label


if __name__ == '__main__':
    unittest.main()
