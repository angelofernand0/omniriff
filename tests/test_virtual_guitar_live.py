"""Live demo signal-path, real network control, and lifecycle checks."""
import asyncio
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
from websockets.asyncio.client import connect

from audio import Engine, EngineConfig
from engine.runtime import Runtime
from tools.virtual_guitar.live import Demo, LiveSource, make_server


class LiveSignalTests(unittest.TestCase):
    def setUp(self):
        self.sr, self.block = 16000, 256
        signal = (0.2 * np.sin(np.arange(self.sr) * 2 * np.pi * 220 / self.sr)).astype(np.float32)
        self.source = LiveSource(signal, self.sr, self.block, volume=1)
        self.audio = Engine(EngineConfig(samplerate=self.sr))
        self.out = np.zeros((self.block, 2), np.float32)

    def process(self, blocks=10):
        for _ in range(blocks):
            self.source.process(self.audio, self.out)
        return float(np.max(np.abs(self.out)))

    def test_pause_silences_input_but_keeps_recorded_loop_playing(self):
        self.audio.toggle_loop()
        self.assertGreater(self.process(40), 0.05)
        self.audio.toggle_loop()
        self.process()
        self.source.playing = False
        self.assertGreater(self.process(40), 0.05)
        self.assertEqual(self.audio.snapshot()['loop']['state'], 'playing')
        position = self.source.position
        self.process()
        self.assertEqual(position, self.source.position)
        self.audio.toggle_loop()
        self.assertLess(self.process(40), 1e-5)

    def test_listening_mute_does_not_stop_dsp_or_clip(self):
        self.assertGreater(self.process(), 0.05)
        before = self.audio.snapshot()['blocks']
        self.source.volume = 0
        self.assertEqual(self.process(), 0)
        self.assertGreater(self.audio.snapshot()['blocks'], before)
        self.source.volume = 1
        self.assertGreater(self.process(100), 0.05)  # wraps source
        self.assertTrue(np.all(np.isfinite(self.out)))
        self.assertEqual(self.audio.snapshot()['clipped_samples'], 0)

    def test_rejects_empty_or_nonfinite_sources(self):
        for source in ([], [float('nan')], [[1, 2]]):
            with self.assertRaises(ValueError):
                LiveSource(source, self.sr, self.block)


class LiveNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.audio = Engine(EngineConfig(samplerate=16000))
        source = LiveSource(np.ones(1600, np.float32) * 0.1, 16000, 256)
        self.runtime = Runtime(self.audio, udp_port=0, ws_port=0)
        await self.runtime.start()
        for _ in range(100):
            if self.runtime.server is not None and self.runtime.udp is not None:
                break
            await asyncio.sleep(0.01)
        self.demo = Demo(source, self.audio, self.runtime, label='TEST', headless=True)
        self.http = make_server(self.demo, 0)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.http.server_port}'
        self.out = np.zeros((256, 2), np.float32)

        async def pump():
            while True:
                self.demo.drain()
                source.process(self.audio, self.out)
                await asyncio.sleep(0.005)
        self.pump = asyncio.create_task(pump())

    async def asyncTearDown(self):
        self.pump.cancel()
        await asyncio.gather(self.pump, return_exceptions=True)
        await self.runtime.close()
        await asyncio.to_thread(self.http.shutdown)
        self.http.server_close()
        self.thread.join(2)

    async def request(self, path, data=None, origin=None):
        def send():
            headers = {'Content-Type': 'application/json'}
            if origin:
                headers['Origin'] = origin
            req = Request(self.url + path, data=None if data is None else json.dumps(data).encode(), headers=headers)
            try:
                with urlopen(req, timeout=3) as response:
                    return response.status, response.read()
            except HTTPError as exc:
                return exc.code, exc.read()
        return await asyncio.to_thread(send)

    async def test_http_controls_and_dashboard_ws_reach_same_audio(self):
        status, _ = await self.request('/api/command', {'action': 'preset', 'value': 'space'})
        self.assertEqual(status, 200)
        async with connect(f'ws://127.0.0.1:{self.runtime.ws_port}') as ws:
            state = json.loads(await ws.recv())
            self.assertEqual(state['reverb']['target'], 0.75)
            self.assertEqual(state['controls']['accepted'], 2)
            await ws.send(json.dumps(dict(version=1, source='dashboard', seq=1,
                                          timestamp_ms=self.runtime.router.clock(),
                                          type='parameter', control='filter', value=0.1, confidence=1)))
            for _ in range(20):
                state = json.loads(await ws.recv())
                if state['filter']['target'] == 0.1:
                    break
            self.assertEqual(state['filter']['target'], 0.1)
        before = self.audio.snapshot()['blocks']
        await asyncio.sleep(0.05)
        self.assertGreater(self.audio.snapshot()['blocks'], before)  # UI disconnect does not stop audio
        status, _ = await self.request('/api/command', {'action': 'bypass'})
        self.assertEqual(status, 200)
        await asyncio.sleep(0.03)
        self.assertTrue(self.audio.snapshot()['bypass'])
        status, body = await self.request('/api/state')
        state = json.loads(body)
        self.assertTrue(state['headless'])
        self.assertNotIn('vision', state['engine']['sources'])
        self.assertNotIn('arduino', state['engine']['sources'])

    async def test_rejects_bad_controls_cross_origin_and_repository_reads(self):
        for data in ({'action': 'volume', 'value': 8}, {'action': 'filter', 'value': True},
                     {'action': 'volume', 'value': float('nan')}, [], {'action': 'unknown'}):
            status, _ = await self.request('/api/command', data)
            self.assertEqual(status, 400)
        status, _ = await self.request('/api/command', {'action': 'bypass'}, origin='https://example.com')
        self.assertEqual(status, 403)
        for path in ('/.env', '/.git/config', '/dashboard/../../README.md'):
            status, _ = await self.request(path)
            self.assertEqual(status, 404)
        for path in ('/', '/app.js', '/style.css', '/dashboard/', '/dashboard/app.js'):
            status, _ = await self.request(path)
            self.assertEqual(status, 200)


if __name__ == '__main__':
    unittest.main()
