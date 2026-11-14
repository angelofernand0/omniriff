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
    def run_session(self):
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
                # Riff goes to FX and takes the effects off while it says so: no approval to wait for
                ask = await until(lambda f: f['target'] == 'bypass')
                await until(lambda f: any(a['what'] == 'rig_control bypass' and a['status'] == 'done' for a in f['activity']))
                await until(lambda f: f['state'] == 'listening')         # "tap the pedal when you're ready"
                await q.put(state('recording', bypass=True))             # the drill take
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
        self.assertIsNone(ask['awaiting_approval'])                  # SM review 4: no waiting for a yes
        from tools.sim.coach import APPROVE_CUE
        self.assertEqual(ask['cue'], APPROVE_CUE)
        self.assertTrue(done['before_after']['improved'])
        whos = {a['who'] for f in frames for a in f['activity']}
        self.assertEqual(whos, {'ears', 'eyes', 'coach'})          # the harness is visible
        # bypass on while Riff says so, back off after the drill; coach source, schema-valid envelopes
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

    def test_full_session_flow(self):
        # ROADMAP §1 "How you use it": take → drill 1 → drill 2 → wrap-up → PLAY → Y → new round
        from tools.sim.coach import DRILL_CUE

        async def go():
            from websockets.asyncio.client import connect
            q: asyncio.Queue = asyncio.Queue()

            async def states():
                while True:
                    yield await q.get()
            port = asyncio.get_running_loop().create_future()
            task = asyncio.create_task(run_scripted_coach(0, udp_port=None, pace=0, states=states(), ready=port.set_result))
            seen = []
            async with connect(f'ws://127.0.0.1:{await port}') as ws:
                async def until(pred):
                    while True:
                        f = json.loads(await asyncio.wait_for(ws.recv(), 2))
                        if f['type'] != 'coach.frame':
                            continue
                        seen.append(f)
                        if pred(f):
                            return f
                take = lambda: [q.put_nowait(state(s)) for s in ('recording', 'playing')]  # noqa: E731
                q.put_nowait(state('idle'))
                take()
                await until(lambda f: f['state'] == 'listening' and f['cue'] == DRILL_CUE)   # drill 1 set up
                take()                                                              # drill 1 take
                d2 = await until(lambda f: (f.get('session') or {}).get('drill', {}) and f['session']['drill']['step'] == 2)
                take()                                                              # drill 2 take
                play = await until(lambda f: (f.get('session') or {}).get('mode') == 'play')
                take()                                                              # PLAY: the pedal just loops
                await asyncio.sleep(0.05)
                await ws.send(json.dumps({'version': 1, 'type': 'coach.approve', 'timestamp_ms': 1, 'approval_id': 'again'}))
                again = await until(lambda f: f.get('session') is None and f['state'] == 'idle')
            task.cancel()
            return seen, d2, play, again

        seen, d2, play, again = asyncio.run(go())
        for f in seen:
            self.assertEqual([e.message for e in COACH.iter_errors(f)], [], f)
        self.assertEqual([p['status'] for p in d2['session']['plan']], ['done', 'now'])
        self.assertEqual([p['status'] for p in play['session']['plan']], ['done', 'done'])
        self.assertTrue(play['session']['summary'])
        self.assertTrue(play['session']['last_time'])
        self.assertEqual(play['session']['metric']['history'], [430.0, 120.0, 110.0])
        from tools.sim.coach import ROUND_CUE
        self.assertEqual(again['cue'], ROUND_CUE)

    def test_player_tells_riff_the_goal(self):
        # coach.say before the first take: the player's own words become the session goal
        async def go():
            from websockets.asyncio.client import connect
            q: asyncio.Queue = asyncio.Queue()

            async def states():
                while True:
                    yield await q.get()
            port = asyncio.get_running_loop().create_future()
            task = asyncio.create_task(run_scripted_coach(0, udp_port=None, pace=0, states=states(), ready=port.set_result))
            async with connect(f'ws://127.0.0.1:{await port}') as ws:
                async def until(pred):
                    while True:
                        f = json.loads(await asyncio.wait_for(ws.recv(), 2))
                        if f['type'] == 'coach.frame' and pred(f):
                            return f
                q.put_nowait(state('idle'))
                await until(lambda f: f['state'] == 'idle')
                said = {'version': 1, 'type': 'coach.say', 'timestamp_ms': 1, 'via': 'voice',
                        'text': "Oh, Riff, I've been struggling with this G to C change"}
                self.assertEqual([e.message for e in COACH.iter_errors(said)], [])
                await ws.send(json.dumps(said))
                got = await until(lambda f: (f.get('session') or {}).get('goal'))
                for s in ('recording', 'playing'):
                    q.put_nowait(state(s))
                diag = await until(lambda f: f.get('drill_card'))
            task.cancel()
            return got, diag

        got, diag = asyncio.run(go())
        from tools.sim.coach import GOAL_CUE
        self.assertEqual(got['cue'], GOAL_CUE)
        self.assertEqual(got['session']['goal'], "I've been struggling with this G to C change")
        self.assertEqual(diag['session']['goal'], "I've been struggling with this G to C change")
        self.assertTrue(any('/journal/' in a['what'] for a in got['activity']))

    def test_riff_takes_effects_off_as_it_says_so(self):
        self.check(*self.run_session())

    def test_riff_works_long_enough_to_watch(self):
        # SM review 4: the deep agent's steps stay up long enough to read (diagnosis ~10 s at pace 1)
        import inspect
        from tools.sim.coach import ScriptedSession
        src = inspect.getsource(ScriptedSession.diagnose)
        waits = [float(x) for x in __import__('re').findall(r'self\.wait\(([\d.]+)\)', src)]
        self.assertGreaterEqual(sum(waits), 9.0)
        self.assertGreaterEqual(len(waits), 5)


if __name__ == '__main__':
    unittest.main()
