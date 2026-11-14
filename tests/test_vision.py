import unittest
from vision.control import Controller
import asyncio
import json
from pathlib import Path
import socket
import time

import numpy as np
from jsonschema import Draft202012Validator
from websockets.asyncio.client import connect
from audio import Engine
from engine.runtime import Runtime
from vision.tracking import HandSelector


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

    def test_relative_clutch_picks_up_without_position_jump(self):
        c = Controller(relative=True, rate=60, deadband=0)
        c.update(.8, .6, .9, 0, 0)
        engage = c.update(.4, .1, .9, .1, 100)
        self.assertEqual(engage['value'], 1.0)
        c.update(.8, .6, .9, .2, 200)
        reengage = c.update(.4, .1, .9, .3, 300)
        self.assertEqual(reengage['value'], 1.0)
        darker = c.update(.5, .1, .9, .4, 400)
        self.assertLess(darker['value'], 1.0)
        self.assertGreater(darker['value'], 0.0)

    def test_relative_reverb_picks_up_from_zero(self):
        c = Controller(control='reverb', relative=True, rate=60, deadband=0)
        c.update(.8, .6, .9, 0, 0)
        engage = c.update(.4, .1, .9, .1, 100)
        self.assertEqual(engage['value'], 0.0)
        changed = c.update(.3, .1, .9, .2, 200)
        self.assertGreater(changed['value'], 0.0)

    def test_pinch_hysteresis_ignores_threshold_jitter(self):
        c = Controller(rate=60, deadband=0)
        c.update(.8, .6, .9, 0, 0)  # Arm with an open hand.
        self.assertIsNone(c.update(.5, .3, .9, .1, 100))  # Not pinched enough.
        self.assertTrue(c.update(.5, .25, .9, .2, 200)['value'] == 0.5)
        c.update(.4, .3, .9, .3, 300)  # In the hysteresis band: remain engaged.
        self.assertTrue(c.active)
        c.update(.4, .44, .9, .4, 400)
        self.assertTrue(c.active)
        self.assertIsNone(c.update(.4, .45, .9, .5, 500))  # Release threshold.
        self.assertFalse(c.active)
        self.assertIsNone(c.update(.4, .3, .9, .6, 600))  # Band alone cannot re-engage.
        self.assertFalse(c.active)
        c.update(.4, .25, .9, .7, 700)
        self.assertTrue(c.active)


class HandSelectorTests(unittest.TestCase):
    def test_follows_same_wrist_when_detection_order_changes(self):
        tracker = HandSelector()
        self.assertEqual(tracker.select([(.2, .4), (.8, .4)]), 0)
        # Detector order flips. Select the wrist near the previous center.
        self.assertEqual(tracker.select([(.79, .41), (.22, .42)]), 1)
        self.assertEqual(tracker.center, (.22, .42))

    def test_rejects_far_hand_until_old_track_is_forgotten(self):
        tracker = HandSelector(max_jump=.2, forget_after=3)
        self.assertEqual(tracker.select([(.1, .2)]), 0)
        self.assertIsNone(tracker.select([(.8, .8)]))
        self.assertIsNone(tracker.select([(.8, .8)]))
        self.assertIsNone(tracker.select([(.8, .8)]))
        # After the old identity expires, the next frame starts a new track.
        self.assertEqual(tracker.select([(.8, .8)]), 0)

    def test_invalid_coordinates_fail_closed(self):
        tracker = HandSelector()
        self.assertIsNone(tracker.select([(float('nan'), .5)]))
        self.assertIsNone(tracker.select([(-.1, .5)]))

    def test_tracker_configuration_is_validated(self):
        for kwargs in ({'max_jump': 0}, {'max_jump': float('nan')}, {'forget_after': 0}):
            with self.assertRaises(ValueError):
                HandSelector(**kwargs)

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


class VisionRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_controller_udp_engine_and_dashboard_state(self):
        audio = Engine()
        runtime = Runtime(audio, udp_port=0, ws_port=0)
        await runtime.start()
        for _ in range(100):
            if runtime.server and runtime.udp:
                break
            await asyncio.sleep(.01)
        self.assertIsNotNone(runtime.server)
        self.assertIsNotNone(runtime.udp)
        signal = np.zeros(128, np.float32)
        output = np.zeros((128, 2), np.float32)
        schema = json.loads((Path(__file__).resolve().parents[1] / 'protocol/state.schema.json').read_text())
        validator = Draft202012Validator(schema)
        control = Controller(rate=60, deadband=0)
        base = time.monotonic()
        control.update(.8, .6, .9, base, int(time.time() * 1000))
        event = control.update(.4, .1, .9, base + .05, int(time.time() * 1000))
        self.assertIsNotNone(event)
        try:
            async with connect(f'ws://127.0.0.1:{runtime.ws_port}') as ws:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    sender.sendto(json.dumps(event).encode(), ('127.0.0.1', runtime.udp_port))
                for _ in range(20):
                    audio.process(signal, output)
                    state = json.loads(await asyncio.wait_for(ws.recv(), 1))
                    validator.validate(state)
                    if state['controls']['accepted']:
                        break
                self.assertEqual(state['controls']['accepted'], 1)
                self.assertEqual(state['filter']['target'], event['value'])
                self.assertIn('vision', state['sources'])
        finally:
            await runtime.close()
