"""Scripted coach session (tools/sim/coach.py): schema-valid, labelled, reacts to pedal and dashboard.

Everything here is simulated: injected engine states, no AI, no audio.
"""
import asyncio
import json
import socket
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.sim.coach import run_scripted_coach

ROOT = Path(__file__).resolve().parents[1]
COACH = Draft202012Validator(json.loads((ROOT / 'protocol/coach.schema.json').read_text()))


def state(loop, bypass=False):
    return {'bypass': bypass, 'loop': {'state': loop, 'seconds': 0, 'max_seconds': 30}}


class ScriptedCoachTests(unittest.TestCase):
    def run_session(self, approve_with):
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(('127.0.0.1', 0))
        udp.setblocking(False)

        async def go():
            from websockets.asyncio.client import connect
            q: asyncio.Queue = asyncio.Queue()

            async def states():
                while True:
                    yield await q.get()

            port = asyncio.get_running_loop().create_future()
            task = asyncio.create_task(run_scripted_coach(0, udp_port=udp.getsockname()[1], pace=0,
                                                          states=states(), ready=port.set_result))
            frames = []
            async with connect(f'ws://127.0.0.1:{await port}') as ws:
                async def until(pred, limit=2.0):
                    end = asyncio.get_running_loop().time() + limit
                    while True:
                        f = json.loads(await asyncio.wait_for(ws.recv(), end - asyncio.get_running_loop().time()))
                        frames.append(f)
                        if pred(f):
                            return f

                await until(lambda f: f['state'] == 'idle')
                for s in ('idle', 'recording', 'playing'):          # take 1 by pedal
                    await q.put(state(s))
                ask = await until(lambda f: f['awaiting_approval'] is not None)
                if approve_with == 'dashboard':
                    await ws.send(json.dumps({'version': 1, 'type': 'coach.approve', 'timestamp_ms': 1,
                                              'approval_id': ask['awaiting_approval']['id']}))
                    await until(lambda f: f['awaiting_approval'] is None)
                    await q.put(state('recording', bypass=True))
                else:
                    await q.put(state('recording'))                  # the pedal is the "go"
                    await until(lambda f: f['awaiting_approval'] is None)
                    await q.put(state('recording', bypass=True))
                await q.put(state('playing', bypass=True))
                done = await until(lambda f: f['state'] == 'pleased')
            task.cancel()
            return frames, ask, done

        try:
            frames, ask, done = asyncio.run(go())
            sent = []
            while True:
                try:
                    sent.append(json.loads(udp.recv(4096)))
                except BlockingIOError:
                    break
        finally:
            udp.close()
        return frames, ask, done, sent

    def check(self, frames, ask, done, sent):
        for f in frames:
            self.assertEqual([e.message for e in COACH.iter_errors(f)], [], f)
            self.assertTrue(f['scripted'])                         # always labelled as scripted
        self.assertEqual(ask['drill_card']['skill'], 'keep-the-hand-moving')
        self.assertEqual(ask['target'], 'bypass')
        self.assertTrue(done['before_after']['improved'])
        whos = {a['who'] for f in frames for a in f['activity']}
        self.assertEqual(whos, {'ears', 'eyes', 'coach'})          # the harness is visible
        # bypass on after approval, back off after the drill; coach source, schema-valid envelopes
        self.assertEqual([(e['source'], e['control']) for e in sent], [('coach', 'bypass'), ('coach', 'bypass')])

    def test_holds_a_line_until_it_is_said(self):
        # Riff never cuts itself off: the next step waits for the measured length of the line + a pause
        from tools.sim.coach import CoachFeed, ScriptedSession, PAUSE_S

        async def go():
            s = ScriptedSession(CoachFeed(), None, pace=1.0)
            s.say(cue='Keep it swinging.')
            s.heard('Keep it swinging.', 0.2)                  # the voice says it's 0.2 s long
            t0 = asyncio.get_running_loop().time()
            await s.until_quiet()
            return asyncio.get_running_loop().time() - t0

        waited = asyncio.run(go())
        self.assertGreaterEqual(waited, 0.2 + PAUSE_S - 0.05)
        self.assertLess(waited, 0.2 + PAUSE_S + 0.3)

    def test_pedal_approves(self):
        self.check(*self.run_session('pedal'))

    def test_dashboard_approves(self):
        self.check(*self.run_session('dashboard'))


if __name__ == '__main__':
    unittest.main()
