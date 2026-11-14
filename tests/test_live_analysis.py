import asyncio
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

import numpy as np
from jsonschema import Draft202012Validator

from audio import Engine
from engine.live import LiveAnalysis
from engine.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
BASE = 1800000000000


class LiveWindowTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.end = 0
        self.hits = []
        owner = self
        class Audio:
            def snapshot_input(self, seconds):
                return np.zeros(2000,np.float32),owner.end,1000
        def detect(window,rate):
            start = self.end-len(window)
            return np.array([frame-start for frame in self.hits if start<=frame<self.end])
        self.live = LiveAnalysis(Audio(),clock=lambda:BASE+round(self.now*1000),
                                 monotonic=lambda:self.now,detector=detect)
        self.live.update()

    def advance(self,end,elapsed=.1):
        self.end = end
        self.now += elapsed
        self.live.update()
        return self.live.snapshot()

    def test_overlap_and_trailing_onset_are_counted_once(self):
        self.hits = [180,280]
        self.assertEqual(self.advance(200,.2)['strums_last_s'],0)  # tail waits for context
        self.assertEqual(self.advance(300)['strums_last_s'],1)     # frame180 predates old end200
        state = self.advance(400)
        self.assertEqual(state['strums_last_s'],2)
        self.assertEqual(state['last_strum_ms'],BASE+280)
        self.assertEqual(self.advance(500)['strums_last_s'],2)
        self.assertEqual(self.live.snapshot()['last_strum_ms'],BASE+280)
        self.assertEqual(self.advance(1200)['strums_last_s'],1)

    def test_steady_requires_evidence_and_reports_a_long_gap(self):
        self.hits = [100,400,700]
        self.assertIsNone(self.advance(200,.2)['steady'])
        self.assertIsNone(self.advance(500,.3)['steady'])
        self.assertTrue(self.advance(800,.3)['steady'])
        self.assertFalse(self.advance(1300,.2)['steady'])
        self.assertIsNone(self.advance(2400)['steady'])

    def test_stall_reset_and_shutdown_do_not_republish_buffered_onsets(self):
        self.hits = [100]
        self.assertEqual(self.advance(200,.2)['strums_last_s'],1)
        self.now += .51
        self.assertIsNone(self.live.snapshot())

        self.live.update()
        self.assertIsNone(self.live.snapshot())
        self.assertIsNone(self.advance(300)['last_strum_ms'])
        self.end = 0
        self.now += .1
        self.live.update()
        self.assertIsNone(self.live.snapshot())
        self.hits = []
        self.assertEqual(self.advance(100)['strums_last_s'],0)
        self.live.stop()
        self.assertIsNone(self.live.snapshot())

    def test_valid_silence_clears_onset_and_steady_lights(self):
        self.hits = [100,400,700]
        self.advance(200,.2)
        self.advance(500,.3)
        self.assertTrue(self.advance(800,.3)['steady'])
        self.assertEqual(self.advance(1800),dict(strums_last_s=0,last_strum_ms=None,steady=None))

    def test_live_shape_is_optional_and_strict_when_present(self):
        schema = json.loads((ROOT/'protocol/state.schema.json').read_text())
        self.assertNotIn('live',schema['required'])
        validator = Draft202012Validator(schema['properties']['live'])
        validator.validate(self.advance(100))
        for state in ({'strums_last_s':-1,'last_strum_ms':None,'steady':None},
                      {'strums_last_s':0,'last_strum_ms':-1,'steady':None},
                      {'strums_last_s':0,'last_strum_ms':None,'steady':'unknown'}):
            self.assertFalse(validator.is_valid(state))

    def test_invalid_input_cannot_be_published_as_silence(self):
        with patch.object(self.live.audio,'snapshot_input',return_value=(np.full(2000,np.nan),100,1000)):
            with self.assertRaises(ValueError): self.live.update()
        self.assertIsNone(self.live.snapshot())

    def test_real_engine_and_ears_keep_pick_attacks_near_poll_boundaries(self):
        rate = 48000
        audio = Engine()
        times = [.198,.598,.998,1.398,1.798]
        signal = np.zeros(round(2.3*rate),np.float32)
        rng = np.random.default_rng(7)
        for seconds in times:
            start = round(seconds*rate)
            pick = rng.normal(0,.2,480)*np.exp(-np.arange(480)/100)
            signal[start:start+480] = pick.astype(np.float32)
        end = 0
        live = LiveAnalysis(audio,clock=lambda:BASE+round(end/rate*1000),monotonic=lambda:end/rate)
        live.update()
        seen = []
        next_poll = 4800
        for start in range(0,len(signal),128):
            block = signal[start:start+128]
            audio.process(block,np.zeros((len(block),2),np.float32))
            end = start+len(block)
            if end>=next_poll:
                live.update()
                state = live.snapshot()
                if state and state['last_strum_ms'] is not None and (not seen or state['last_strum_ms']!=seen[-1]):
                    seen.append(state['last_strum_ms'])
                next_poll += 4800
        self.assertEqual(len(seen),len(times),seen)
        for actual,seconds in zip(seen,times):
            self.assertAlmostEqual(actual-BASE,seconds*1000,delta=15)


class LiveRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_analysis_failure_stall_and_close_do_not_break_controls(self):
        from websockets.asyncio.client import connect
        audio = Engine()
        runtime = Runtime(audio,udp_port=0,ws_port=0)
        stop = threading.Event()
        thread_ids = []
        def detector(window,rate):
            thread_ids.append(threading.get_ident())
            return np.array([])
        runtime.live.detector = detector
        # Pre-fill the input history (live analysis needs a full 2 s window) so the
        # test doesn't depend on the renderer keeping real time under suite load.
        for _ in range(int(2.2*audio.config.samplerate/128)+1):
            audio.process(np.zeros(128,np.float32),np.zeros((128,2),np.float32))
        def render():
            while not stop.wait(.003):
                audio.process(np.zeros(128,np.float32),np.zeros((128,2),np.float32))
        renderer = threading.Thread(target=render)
        renderer.start()
        async def until(predicate):
            deadline = asyncio.get_running_loop().time()+10
            while not predicate():
                if asyncio.get_running_loop().time()>deadline: self.fail(str(runtime.snapshot()))
                await asyncio.sleep(.01)
        try:
            with patch.object(audio,'snapshot_input',side_effect=OSError('synthetic unavailable')), \
                    self.assertLogs('omniriff.live',level='WARNING') as logs:
                await runtime.start()
                await until(lambda: runtime.server is not None)
                async with connect(f'ws://127.0.0.1:{runtime.ws_port}',origin='http://localhost:8080') as ws:
                    await ws.send(json.dumps(dict(version=1,source='dashboard',seq=0,timestamp_ms=runtime.router.clock(),
                                                  type='action',control='bypass')))
                    await until(lambda: audio.snapshot()['bypass'])
                await asyncio.sleep(.22)
                self.assertNotIn('live',runtime.snapshot())
                self.assertEqual(len(logs.output),1)
            await until(lambda: 'live' in runtime.snapshot())
            state = runtime.snapshot()
            Draft202012Validator(json.loads((ROOT/'protocol/state.schema.json').read_text())).validate(state)
            self.assertTrue(thread_ids)
            self.assertNotIn(threading.get_ident(),thread_ids)
            self.assertNotIn(renderer.ident,thread_ids)
            stop.set(); renderer.join(1)
            await until(lambda: 'live' not in runtime.snapshot())  # stalled input is withdrawn
        finally:
            stop.set(); renderer.join(1)
            await runtime.close()
        self.assertNotIn('live',runtime.snapshot())
