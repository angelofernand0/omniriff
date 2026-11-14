"""Offline process/approval integration; never calls a model or microphone."""
import asyncio
from importlib.util import find_spec
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest

import numpy as np
from jsonschema import Draft202012Validator

from audio import Engine, EngineConfig
from audio.takes import TakeWriter
from coach.fixtures.generate import render_audio, timing, CHORD_CHANGE_INDICES, SAMPLERATE
from engine.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
OPTIONAL = all(find_spec(name) is not None for name in ('langchain_core','langgraph'))


def captured_fixture(directory):
    """Feed the real Engine/--take-dir writer; keep raw synthetic takes temporary."""
    times,_ = timing(400)
    signal = render_audio(times)
    audio = Engine(EngineConfig(samplerate=SAMPLERATE))
    directory.mkdir()
    writer = TakeWriter(audio,directory)
    audio.toggle_loop()
    for start in range(0,len(signal),128):
        block = signal[start:start+128]
        audio.process(block,np.zeros((len(block),2),np.float32))
    audio.toggle_loop()
    audio.process(np.zeros(128,np.float32),np.zeros((128,2),np.float32))
    wav = writer.poll()
    if wav is None: raise RuntimeError('engine did not capture the planted take')
    return audio,times[CHORD_CHANGE_INDICES[0]]*1000


@unittest.skipUnless(OPTIONAL,'optional coach deps (langchain_core/langgraph) not installed')
class CoachProcessIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_planted_take_waits_for_matching_approval_then_sends_one_control(self):
        from websockets.asyncio.client import connect
        with tempfile.TemporaryDirectory(prefix='omniriff-coach-gate-') as folder:
            root = Path(folder)
            audio,planted_ms = await asyncio.to_thread(captured_fixture,root/'takes')
            runtime = Runtime(audio,udp_port=0,ws_port=0,live_analysis=False)
            received = []
            original_ingest = runtime.router.ingest
            def capture(raw,**kwargs):
                received.append(json.loads(raw))
                return original_ingest(raw,**kwargs)
            runtime.router.ingest = capture
            stop = threading.Event()
            def render():
                inp = np.zeros(128,np.float32); out = np.zeros((128,2),np.float32)
                while not stop.wait(.008): audio.process(inp,out)
            renderer = threading.Thread(target=render)
            child = None
            feed_port = None
            log = root/'worker.log'
            async def until(predicate,timeout=10):
                deadline = asyncio.get_running_loop().time()+timeout
                while not predicate():
                    if asyncio.get_running_loop().time()>deadline:
                        self.fail(log.read_text() if log.exists() else 'integration timeout')
                    await asyncio.sleep(.01)
            try:
                await runtime.start()
                await until(lambda: runtime.udp is not None and runtime.server is not None)
                udp_port,ws_port = runtime.udp_port,runtime.ws_port
                renderer.start()
                ready,go,result = root/'ready.json',root/'go',root/'result.json'
                with log.open('w') as output:
                    child = await asyncio.create_subprocess_exec(
                        sys.executable,str(ROOT/'tests/coach_offline_worker.py'),
                        '--take-dir',str(root/'takes'),'--workspace',str(root/'workspace'),
                        '--state-port',str(ws_port),'--control-port',str(udp_port),
                        '--ready',str(ready),'--go',str(go),'--result',str(result),
                        cwd=ROOT,stdout=output,stderr=output)
                await until(ready.exists)
                feed_port = json.loads(ready.read_text())['port']
                validator = Draft202012Validator(json.loads((ROOT/'protocol/coach.schema.json').read_text()))
                frames = []
                async with connect(f'ws://127.0.0.1:{feed_port}',origin='http://localhost:8080') as ws:
                    go.touch()
                    async def approval():
                        while True:
                            frame = json.loads(await ws.recv())
                            validator.validate(frame)
                            if frame['type']!='coach.frame': continue
                            self.assertFalse(frame['scripted'])
                            frames.append(frame)
                            if frame['awaiting_approval']: return frame['awaiting_approval']
                    pending = await asyncio.wait_for(approval(),10)
                    cues = [frame['cue'] for frame in frames if frame.get('cue','') and 'Measured hesitation' in frame['cue']]
                    self.assertTrue(cues,frames)
                    self.assertTrue(any(frame['drill_card'] is not None for frame in frames))
                    self.assertEqual(pending['actions'],[{'control':'bypass'}])
                    self.assertEqual(received,[])
                    decision = dict(version=1,type='coach.approve',timestamp_ms=int(time.time()*1000),approval_id='wrong-id')
                    await ws.send(json.dumps(decision))
                    await asyncio.sleep(.2)
                    self.assertEqual(received,[],'wrong approval id must not reach the engine')
                    decision['approval_id'] = pending['id']
                    decision['timestamp_ms'] = int(time.time()*1000)
                    await ws.send(json.dumps(decision))
                    await until(lambda: len(received)>=1 and audio.snapshot()['bypass'])
                    self.assertEqual(await asyncio.wait_for(child.wait(),10),0,log.read_text())
                await asyncio.sleep(.1)
                self.assertEqual(len(received),1)
                message = received[0]
                Draft202012Validator(json.loads((ROOT/'protocol/control.schema.json').read_text())).validate(message)
                self.assertEqual((message['source'],message['type'],message['control']),('coach','action','bypass'))
                self.assertEqual(runtime.router.counts['accepted'],1)
                self.assertEqual(runtime.router.counts['duplicate'],0)
                proof = json.loads(result.read_text())
                self.assertEqual(proof['sent'],received)
                self.assertAlmostEqual(proof['finding']['at_ms'],planted_ms,delta=30)
                self.assertTrue(any(f"{proof['finding']['at_ms']:.1f} ms" in cue for cue in cues))
            finally:
                if child is not None and child.returncode is None:
                    child.kill()
                    await asyncio.wait_for(child.wait(),5)
                stop.set()
                if renderer.ident: renderer.join(2)
                await runtime.close()
            # No live servers remain; SO_REUSEADDR permits closed TCP TIME_WAIT.
            for port in (ws_port,feed_port):
                if port is None: continue
                with socket.socket() as probe:
                    self.assertNotEqual(probe.connect_ex(('127.0.0.1',port)),0)
                with socket.socket() as probe:
                    probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                    probe.bind(('127.0.0.1',port)); probe.listen()
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
                probe.bind(('127.0.0.1',udp_port))
