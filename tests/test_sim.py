"""tools/sim and dashboard checks. Simulated input only; no hardware or latency claims."""
import asyncio
import json
import unittest
import urllib.request
import threading
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator

from tools.sim.events import Sender, VALIDATOR
from tools.sim.synth import SyntheticGuitar

ROOT = Path(__file__).resolve().parents[1]
STATE = Draft202012Validator(json.loads((ROOT / 'protocol/state.schema.json').read_text()))


class EventTests(unittest.TestCase):
    def test_envelopes_are_valid_and_strictly_increasing(self):
        s = Sender('manual', port=9)
        try:
            events = [s.envelope('loop'), s.envelope('bypass'), s.envelope('filter', 0.4), s.envelope('reverb', 1.0, 0.9)]
        finally:
            s.close()
        for e in events:
            self.assertTrue(VALIDATOR.is_valid(e), e)
        seqs = [e['seq'] for e in events]
        self.assertEqual(seqs, sorted(set(seqs)))
        self.assertNotIn('value', events[0])
        self.assertEqual(events[3]['confidence'], 0.9)

    def test_rejects_out_of_range_before_sending(self):
        s = Sender('vision', port=9)
        try:
            with self.assertRaises(Exception):
                s.envelope('filter', 1.5)
        finally:
            s.close()

    def test_new_sender_continues_after_previous_run(self):
        a = Sender('manual', port=9); b = Sender('manual', port=9)
        try:
            first = a.envelope('loop')['seq']
            self.assertGreaterEqual(b.envelope('loop')['seq'], first)
        finally:
            a.close(); b.close()


class SynthTests(unittest.TestCase):
    def test_bounded_finite_and_audible(self):
        g = SyntheticGuitar(48000, bpm=120)
        x = np.concatenate([g.block(256) for _ in range(400)])  # ~2 s
        self.assertTrue(np.all(np.isfinite(x)))
        self.assertLessEqual(float(np.max(np.abs(x))), 0.98)
        self.assertGreater(float(np.max(np.abs(x))), 0.05)

    def test_deterministic(self):
        a = np.concatenate([SyntheticGuitar(seed=3).block(512) for _ in range(1)])
        b = np.concatenate([SyntheticGuitar(seed=3).block(512) for _ in range(1)])
        np.testing.assert_array_equal(a, b)


class RuntimeTests(unittest.TestCase):
    """Real audio.Engine + engine.Runtime on ephemeral ports, driven by the sim."""

    def test_sim_events_drive_engine_and_state_matches_schema(self):
        from audio import Engine
        from engine.runtime import Runtime
        from websockets.asyncio.client import connect

        async def run():
            audio = Engine()
            rt = Runtime(audio, udp_port=0, ws_port=0)
            guitar = SyntheticGuitar(audio.config.samplerate)
            out = np.zeros((256, 2), np.float32)
            await rt.start()
            for _ in range(100):
                if rt.adapters['udp']['status'] == 'running' and rt.adapters['websocket']['status'] == 'running':
                    break
                await asyncio.sleep(0.02)
            pedal, hand = Sender('manual', port=rt.udp_port), Sender('vision', port=rt.udp_port)
            try:
                pedal.send('loop')
                hand.send('reverb', 0.7, 0.9)
                await asyncio.sleep(0.1)
                for _ in range(40):
                    audio.process(guitar.block(256), out)
                async with connect(f'ws://127.0.0.1:{rt.ws_port}') as ws:
                    state = json.loads(await asyncio.wait_for(ws.recv(), 2))
                    # dashboard-style event over the same socket
                    await ws.send(json.dumps(dict(version=1, source='dashboard', seq=1, timestamp_ms=rt.router.clock(), type='action', control='bypass')))
                    await asyncio.sleep(0.15)
                    audio.process(guitar.block(256), out)  # actions apply on the next audio block
                    after = None
                    for _ in range(20):  # skip frames published before the block ran
                        after = json.loads(await asyncio.wait_for(ws.recv(), 2))
                        if after['bypass']:
                            break
                return state, after
            finally:
                pedal.close(); hand.close()
                await rt.close()

        state, after = asyncio.run(run())
        STATE.validate(state)
        self.assertEqual(state['loop']['state'], 'recording')
        self.assertAlmostEqual(state['reverb']['target'], 0.7)
        self.assertGreater(state['input_peak_dbfs'], -60)
        self.assertEqual(state['sources']['vision']['accepted'], 1)
        self.assertTrue(after['bypass'])


class DashboardServeTests(unittest.TestCase):
    def test_serves_static_files(self):
        from dashboard.__main__ import make_server
        server = make_server(0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f'http://127.0.0.1:{server.server_address[1]}/'
            html = urllib.request.urlopen(base, timeout=2).read().decode()
            self.assertIn('app.js', html)
            for name in ('app.js', 'style.css'):
                self.assertEqual(urllib.request.urlopen(base + name, timeout=2).status, 200)
        finally:
            server.shutdown(); server.server_close()

    def test_simulator_server_labels_the_page_and_plain_server_does_not(self):
        from dashboard.__main__ import make_server
        for sim, expected in (('input', '/?ws=x&sim=input'), (None, '/?ws=x')):
            server = make_server(0, sim=sim)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                base = f'http://127.0.0.1:{server.server_address[1]}'
                page = urllib.request.urlopen(base + '/?ws=x', timeout=2)
                self.assertEqual(page.url, base + expected)   # redirected only when simulated
                self.assertIn('id="simChip"', page.read().decode())
                # an explicit flag is kept, and assets are never redirected
                self.assertEqual(urllib.request.urlopen(base + '/?sim=guitar', timeout=2).url, base + '/?sim=guitar')
                self.assertEqual(urllib.request.urlopen(base + '/app.js', timeout=2).url, base + '/app.js')
            finally:
                server.shutdown(); server.server_close()

    def test_cached_sources_cannot_look_online_when_connection_is_down(self):
        script = (ROOT / 'dashboard/app.js').read_text()
        self.assertIn("const online = conn === 'live' && seenAge < ONLINE_MS;", script)
        self.assertIn("box.classList.toggle('active', online && seenAge < ENGAGED_MS);", script)


if __name__ == '__main__':
    unittest.main()
