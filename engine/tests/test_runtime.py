import asyncio
import json
from pathlib import Path
import socket
import unittest
import numpy as np
from jsonschema import Draft202012Validator
from audio import Engine
from engine.router import Router
from engine.runtime import Runtime, SerialDecoder

ROOT = Path(__file__).resolve().parents[2]

def event(seq=0, **kw):
    value = dict(version=1, source='vision', seq=seq, timestamp_ms=10000,
                 type='parameter', control='filter', value=0.2, confidence=0.9)
    value.update(kw)
    return value

def process(audio, blocks=1):
    signal = np.zeros(128, np.float32)
    output = np.empty((128, 2), np.float32)
    for _ in range(blocks): audio.process(signal, output)
    return output


class GateTests(unittest.TestCase):
    def setUp(self):
        self.now = 10000
        self.audio = Engine()
        self.router = Router(self.audio, clock=lambda:self.now, monotonic=lambda:self.now)

    def send(self, value): return self.router.ingest(json.dumps(value))

    def test_replay_actual_fixture_through_audio(self):
        fixtures = json.loads((ROOT/'protocol/examples.json').read_text())
        for fixture in fixtures:
            fixture['timestamp_ms'] = self.now
            self.assertTrue(self.send(fixture))
            process(self.audio, 4)
        state = self.audio.snapshot()
        self.assertEqual(state['filter']['target'], 0.4)
        self.assertEqual(state['loop']['state'], 'recording')
        self.assertEqual(self.router.counts['accepted'], 2)

    def test_freshness_dedupe_confidence_and_malformed(self):
        for value, reason in [(event(timestamp_ms=9749),'stale'), (event(timestamp_ms=10251),'future'),
                              (event(confidence=0.1),'low_confidence')]:
            self.assertFalse(self.send(value))
            self.assertEqual(self.router.counts[reason], 1)
        self.assertTrue(self.send(event(1)))
        self.assertFalse(self.send(event(1)))
        self.assertEqual(self.router.counts['duplicate'], 1)
        self.assertFalse(self.router.ingest(b'not json'))
        self.assertFalse(self.router.ingest(b'x'*4097))
        self.assertFalse(self.router.ingest(json.dumps(event(2, value=float('nan')))))
        self.assertFalse(self.router.ingest(json.dumps(event(2)).replace('0.2', '1e999')))
        self.assertFalse(self.send(event(3, value=True)))
        self.assertEqual(self.router.counts['invalid'], 5)
        process(self.audio)
        self.assertEqual(self.audio.snapshot()['filter']['target'], 0.2)

    def test_udp_restart_and_old_replay(self):
        self.assertTrue(self.send(event(10)))
        self.assertFalse(self.send(event(0)))
        self.now += 1100
        self.assertFalse(self.send(event(0)))  # timestamp stale, not a session reset
        self.assertTrue(self.send(event(0, timestamp_ms=self.now)))
        self.assertEqual(self.router.sources['vision']['session'], 2)
        self.assertFalse(self.send(event(11, timestamp_ms=self.now-10)))

    def test_restart_recovers_when_sequence_zero_was_lost(self):
        self.assertTrue(self.send(event(200)))
        self.now += 100
        self.assertFalse(self.send(event(0, timestamp_ms=self.now)))
        self.now += 1001
        self.assertTrue(self.send(event(21, timestamp_ms=self.now)))
        self.assertEqual(self.router.sources['vision']['session'], 2)
        # Retrying the same action identity after an idle period isn't a restart.
        self.now += 1001
        self.assertFalse(self.send(event(21, timestamp_ms=self.now)))

    def test_equal_zero_action_is_not_replayed_after_idle(self):
        action = dict(version=1, source='dashboard', seq=0, timestamp_ms=self.now,
                      type='action', control='bypass')
        self.assertTrue(self.send(action))
        process(self.audio)
        self.assertTrue(self.audio.snapshot()['bypass'])
        self.now += 1100
        self.assertFalse(self.send(dict(action, timestamp_ms=self.now)))
        process(self.audio)
        self.assertTrue(self.audio.snapshot()['bypass'])
        self.assertEqual(self.router.counts['accepted'], 1)

    def test_replay_loader_rejects_invalid_scripts_before_startup(self):
        import tempfile
        from engine.replay import Replay
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'controls.jsonl'
            for content in ['', 'not JSON', json.dumps(event(value=2)),
                            json.dumps(event())+'\n'+json.dumps(event(1, timestamp_ms=9999)),
                            json.dumps(event())+'\n'+json.dumps(event(timestamp_ms=10010))]:
                path.write_text(content)
                with self.subTest(content=content):
                    with self.assertRaises(ValueError): Replay.load(path)
            path.write_text(json.dumps(event())+'\n'+json.dumps(event(1,timestamp_ms=10010)))
            replay = Replay.load(path)
            self.assertEqual([row[0] for row in replay.entries], [0,10])

    def test_serial_reader_waits_for_one_byte_then_drains_available(self):
        from engine.runtime import read_serial_chunk
        class Port:
            in_waiting = 0
            requests = []
            def read(self, size):
                self.requests.append(size)
                return b'x' * size
        port = Port()
        self.assertEqual(len(read_serial_chunk(port)), 1)
        port.in_waiting = 54
        self.assertEqual(len(read_serial_chunk(port)), 54)
        port.in_waiting = 1000
        self.assertEqual(len(read_serial_chunk(port)), 256)
        self.assertEqual(port.requests, [1,54,256])

    def test_serial_partial_lines_duplicate_reset_and_reconnect(self):
        decoder = SerialDecoder(self.router)
        decoder.connect()
        line = b'{"seq":0,"type":"action","control":"bypass"}\n'
        decoder.feed(line[:12]); process(self.audio)
        self.assertFalse(self.audio.snapshot()['bypass'])
        decoder.feed(line[12:]); process(self.audio)
        self.assertTrue(self.audio.snapshot()['bypass'])
        decoder.feed(line); process(self.audio)
        self.assertTrue(self.audio.snapshot()['bypass'])
        decoder.feed(line.replace(b':0',b':1')); process(self.audio)
        self.assertFalse(self.audio.snapshot()['bypass'])
        decoder.feed(line); process(self.audio)
        self.assertTrue(self.audio.snapshot()['bypass'])
        decoder.connect(); decoder.feed(line); process(self.audio)
        self.assertFalse(self.audio.snapshot()['bypass'])
        decoder.feed(b'x'*5000+b'\n'+b'{}\n')
        self.assertEqual(self.router.counts['invalid'], 2)


class NetworkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.audio = Engine()
        self.runtime = Runtime(self.audio, udp_port=0, ws_port=0)
        await self.runtime.start()
        await self.ready()

    async def asyncTearDown(self): await self.runtime.close()

    async def ready(self):
        for _ in range(100):
            if self.runtime.server and self.runtime.udp: return
            await asyncio.sleep(0.01)
        self.fail(str(self.runtime.adapters))

    async def test_udp_ws_schema_browser_controls_and_disconnect(self):
        from websockets.asyncio.client import connect
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            client.sendto(json.dumps(event(timestamp_ms=self.runtime.router.clock())).encode(), ('127.0.0.1',self.runtime.udp_port))
        finally: client.close()
        validator = Draft202012Validator(json.loads((ROOT/'protocol/state.schema.json').read_text()))
        async with connect(f'ws://127.0.0.1:{self.runtime.ws_port}', origin='http://localhost:5173') as ws:
            first = json.loads(await asyncio.wait_for(ws.recv(), 1))
            validator.validate(first)
            self.assertEqual(first['controls']['accepted'], 1)
            action = dict(version=1, source='dashboard',seq=0,timestamp_ms=self.runtime.router.clock(),type='action',control='bypass')
            await ws.send(json.dumps(action))
            for _ in range(50):
                process(self.audio)
                state = json.loads(await asyncio.wait_for(ws.recv(), 1))
                validator.validate(state)
                if state['bypass']: break
            self.assertTrue(state['bypass'])
        # Stop adapters one by one while the real DSP thread keeps processing.
        import threading
        stop = threading.Event()
        def render():
            while not stop.wait(0.003): process(self.audio)
        worker = threading.Thread(target=render)
        worker.start()
        try:
            for task in self.runtime.tasks.values():
                before = self.audio.snapshot()['blocks']
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                await asyncio.sleep(0.03)
                self.assertGreater(self.audio.snapshot()['blocks'], before)
        finally:
            stop.set(); worker.join(1)

    async def test_serial_device_failure_reopens_with_new_session(self):
        import time
        from unittest.mock import patch
        ports = []
        class FakePort:
            in_waiting = 0
            def __init__(self, *args, **kwargs):
                self.number = len(ports)
                self.reads = 0
                self.closed = False
                ports.append(self)
            def read(self, size):
                self.reads += 1
                if self.reads == 1:
                    return b'{"seq":0,"type":"action","control":"bypass"}\n'
                if self.number == 0: raise OSError('simulated USB disconnect')
                time.sleep(0.01)
                return b''
            def close(self): self.closed = True
        self.runtime.serial_port = 'FAKE'
        with patch('serial.Serial', FakePort):
            task = asyncio.create_task(self.runtime.supervise('serial', self.runtime.run_serial))
            self.runtime.tasks['serial'] = task
            try:
                for _ in range(250):
                    process(self.audio)
                    if self.runtime.router.counts['accepted'] >= 2: break
                    await asyncio.sleep(0.01)
                self.assertGreaterEqual(len(ports), 2)
                self.assertTrue(ports[0].closed)
                self.assertEqual(self.runtime.router.counts['accepted'], 2)
                self.assertEqual(self.runtime.router.sources['arduino']['session'], 2)
                process(self.audio)
                self.assertFalse(self.audio.snapshot()['bypass'])
                self.assertEqual(self.runtime.adapters['serial']['status'], 'running')
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(all(port.closed for port in ports))

    async def test_replay_labels_state_rebases_controls_and_completes(self):
        import tempfile
        from engine.replay import Replay
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'controls.jsonl'
            path.write_text(json.dumps(event(timestamp_ms=1000,value=.25))+'\n'+
                            json.dumps(event(1,timestamp_ms=1010,value=.75)))
            replay = Replay.load(path)
            runtime = Runtime(self.audio, udp_port=0, ws_port=0, replay=replay)
            validator = Draft202012Validator(json.loads((ROOT/'protocol/state.schema.json').read_text()))
            await runtime.start()
            try:
                from websockets.asyncio.client import connect
                for _ in range(100):
                    if runtime.server: break
                    await asyncio.sleep(.01)
                async with connect(f'ws://127.0.0.1:{runtime.ws_port}') as ws:
                    state = json.loads(await asyncio.wait_for(ws.recv(),1))
                    validator.validate(state)
                    self.assertEqual(state['replay']['label'], 'REPLAY')
                await asyncio.wait_for(runtime.tasks['replay'],1)
                process(self.audio)
                state = runtime.snapshot(); validator.validate(state)
                self.assertEqual(state['replay']['status'],'completed')
                self.assertFalse(state['replay']['active'])
                self.assertEqual(state['replay']['position'],2)
                self.assertEqual(state['controls']['accepted'],2)
                self.assertEqual(state['controls']['stale'],0)
                self.assertEqual(state['filter']['target'],.75)
                self.assertEqual(state['adapters']['udp']['status'],'disabled')
                self.assertIn('manual',state['sources'])
            finally: await runtime.close()

    async def test_replay_stop_keeps_label_and_audio_available(self):
        from engine.replay import Replay
        replay = Replay([(0,event()), (60000,event(1))])
        runtime = Runtime(self.audio, udp_port=None, ws_port=None, replay=replay)
        with self.assertLogs('omniriff.replay',level='WARNING') as logs:
            await runtime.start()
            await asyncio.sleep(.01)
            await runtime.close()
        self.assertIn('REPLAY CONTROL MODE', '\n'.join(logs.output))
        self.assertEqual(runtime.snapshot()['replay']['status'],'stopped')
        self.assertEqual(runtime.snapshot()['replay']['label'],'REPLAY')
        self.audio.toggle_bypass(); process(self.audio)
        self.assertTrue(self.audio.snapshot()['bypass'])

    async def test_replay_late_action_is_dropped_not_retimestamped(self):
        from engine.replay import Replay
        router = Router(self.audio, clock=lambda:10000)
        replay = Replay([(0,dict(version=1,source='manual',seq=0,timestamp_ms=0,type='action',control='bypass'))])
        from unittest.mock import patch
        async def delayed_sleep(_): router.clock=lambda:11000
        with patch('engine.replay.asyncio.sleep', delayed_sleep):
            await replay.run(router)
        process(self.audio)
        self.assertEqual(router.counts['stale'],1)
        self.assertFalse(self.audio.snapshot()['bypass'])

    async def test_missing_serial_does_not_stop_other_adapters(self):
        from websockets.asyncio.client import connect
        self.runtime.serial_port = '/no/such/omniriff-device'
        self.runtime.tasks['serial'] = asyncio.create_task(self.runtime.supervise('serial', self.runtime.run_serial))
        await asyncio.sleep(0.15)
        self.assertGreater(self.runtime.adapters['serial']['errors'], 0)
        async with connect(f'ws://127.0.0.1:{self.runtime.ws_port}') as ws:
            state = json.loads(await asyncio.wait_for(ws.recv(), 1))
            self.assertEqual(state['adapters']['websocket']['status'], 'running')
        process(self.audio)
        self.assertGreater(self.audio.snapshot()['blocks'], 0)
