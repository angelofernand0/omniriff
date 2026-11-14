"""Scripted coach session: a coach feed (protocol/coach.schema.json) with no AI behind it.

  python -m tools.sim coach                  # against any running engine (sim or real) on ws 47801
  python -m tools.sim run --demo --coach-sim # inside the simulator

It serves ws://127.0.0.1:47803 like the real coach (coach/, piece D) and reacts to real events:
the engine's loop state (the pedal) and the dashboard's coach.approve / coach.reject. The
diagnosis, numbers and drill are SCRIPTED: every frame says scripted=true and the dashboard must
label it. Two uses: building the dashboard before the coach brain exists, and a labelled fallback
at the demo table if the live coach is unavailable. It may toggle bypass (source "coach") after
the player approves, through the same validated control path as every other source.
"""
from __future__ import annotations

import asyncio
import copy
import json
import time
from pathlib import Path

from jsonschema import Draft202012Validator

from .events import Sender

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = Draft202012Validator(json.loads((ROOT / 'protocol/coach.schema.json').read_text()))

SKILL = 'keep-the-hand-moving'
TAKE_CUE = ("You're late on the G to C change, about 430 milliseconds, because your strumming hand "
            "stops. Keep it swinging through the change.")
APPROVE_CUE = "Effects off so you hear your timing. Tap the pedal when you're ready."
DRILL_CUE = 'Four times through the change, slowly. Keep the hand moving.'
PASS_CUE = "Your longest gap went from 430 to 120 milliseconds. That's the change."
DECLINE_CUE = "No problem, I'll leave your sound as it is."
IDLE_CUE = 'Play me something. Tap the pedal to record.'
AGAIN_CUE = 'Again? Tap the pedal to record.'
PAUSE_S = 0.9   # a beat of silence after Riff finishes a line, before the next thing happens
WORDS_PER_S = 2.6
TODOS = ['Check timing (ears)', 'Check strumming hand (eyes)', 'Pick one drill', 'Set up the rig']


def now_ms() -> int:
    return int(time.time() * 1000)


class CoachFeed:
    """Holds the latest coach.frame, serves it to every client, and queues decisions from them."""

    def __init__(self, session_id: str = 'scripted'):
        self.frame = dict(version=1, type='coach.frame', timestamp_ms=now_ms(), session_id=session_id,
                          take_id=None, state='idle', mood='neutral', target='player', cue=IDLE_CUE,
                          todos=[], drill_card=None, before_after=None, awaiting_approval=None,
                          activity=[], scripted=True)
        self.clients: set = set()
        self.decisions: asyncio.Queue = asyncio.Queue()
        SCHEMA.validate(self.frame)

    def update(self, **changes) -> dict:
        nxt = copy.deepcopy(self.frame)
        nxt.update(changes)
        nxt['timestamp_ms'] = now_ms()
        nxt['activity'] = nxt['activity'][-8:]
        SCHEMA.validate(nxt)  # never publish an invalid frame
        self.frame = nxt
        self._broadcast(nxt)
        return nxt

    def _broadcast(self, msg: dict) -> None:
        data = json.dumps(msg, separators=(',', ':'))
        for ws in list(self.clients):
            asyncio.ensure_future(self._send(ws, data))

    async def _send(self, ws, data: str) -> None:
        try:
            await asyncio.wait_for(ws.send(data), 0.5)
        except Exception:
            self.clients.discard(ws)  # slow or gone viewer; never blocks the session

    async def handler(self, ws) -> None:
        self.clients.add(ws)
        try:
            await ws.send(json.dumps(self.frame, separators=(',', ':')))
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if SCHEMA.is_valid(msg) and msg.get('type') in ('coach.approve', 'coach.reject'):
                    await self.decisions.put(msg)
        except Exception:
            pass
        finally:
            self.clients.discard(ws)

    async def serve(self, port: int = 47803, ready=None) -> None:
        from websockets.asyncio.server import serve
        async with serve(self.handler, '127.0.0.1', port, max_size=4096) as server:
            if ready is not None:
                ready(server.sockets[0].getsockname()[1])
            await asyncio.Future()


async def engine_states(url: str):
    """Yield engine state frames from ws, reconnecting forever. None means the engine is gone."""
    from websockets.asyncio.client import connect
    while True:
        try:
            async with connect(url, max_size=2 ** 20) as ws:
                async for raw in ws:
                    try:
                        yield json.loads(raw)
                    except ValueError:
                        continue
        except Exception:
            pass
        yield None
        await asyncio.sleep(1.0)


def _act(feed: CoachFeed, who: str, what: str, status: str) -> list:
    acts = [a for a in feed.frame['activity'] if not (a['who'] == who and a['what'] == what)]
    return acts + [dict(who=who, what=what, status=status)]


def _todos(done: int, extra: list | None = None) -> list:
    items = [dict(text=t, status='completed' if i < done else 'in_progress' if i == done else 'pending')
             for i, t in enumerate(TODOS)]
    return items + (extra or [])


class ScriptedSession:
    """take 1 → scripted diagnosis + drill proposal → approval → drill take → before/after → again."""

    def __init__(self, feed: CoachFeed, sender: Sender | None, pace: float = 1.0, speak=None):
        self.feed, self.sender, self.pace, self.speak = feed, sender, pace, speak
        self.loop = 'idle'
        self.bypass = False
        self.we_bypassed = False
        self.phase = 'first'      # first take, or 'drill' take after approval
        self.awaiting = None
        self.takes = 0
        self.quiet_at = 0.0       # loop time when the current line (plus a pause) is done
        self.cue_at = 0.0

    async def wait(self, seconds: float) -> None:
        await asyncio.sleep(seconds * self.pace)

    def say(self, **changes) -> None:
        prev = self.feed.frame.get('cue')
        f = self.feed.update(**changes)
        cue = changes.get('cue')
        if cue and cue != prev:
            # hold the line until it has been said: estimated now, measured once the audio exists
            now = asyncio.get_event_loop().time()
            self.cue_at = now
            self.quiet_at = now + max(1.2, len(cue.split()) / WORDS_PER_S) + PAUSE_S
            if self.speak:
                try:
                    self.speak(f['cue'])
                except Exception:
                    pass  # voice never breaks the session

    def heard(self, text: str, seconds: float) -> None:
        """The voice reports the real length of a line once it's rendered."""
        if self.feed.frame.get('cue') == text:
            self.quiet_at = self.cue_at + seconds + PAUSE_S

    async def until_quiet(self) -> None:
        """Wait until Riff has finished the current line and paused. Never cuts a line off."""
        while True:
            rest = self.quiet_at - asyncio.get_event_loop().time()
            if rest <= 0:
                return
            await asyncio.sleep(rest * self.pace if self.pace else 0)
            if not self.pace:
                return

    def take_id(self) -> str:
        return f'take-scripted-{self.takes}'

    # ---- events -------------------------------------------------------
    async def on_state(self, st: dict | None) -> None:
        if st is None:
            self.say(state='asleep', mood='sleepy', target=None, cue='Waiting for the engine.', awaiting_approval=None)
            self.loop = 'offline'
            return
        self.bypass = bool(st.get('bypass'))
        new = (st.get('loop') or {}).get('state', 'idle')
        old, self.loop = self.loop, new
        if old == 'offline':
            self.say(state='idle', mood='neutral', target='player', cue=IDLE_CUE)
        if new == old:
            return
        if new == 'recording':
            if self.awaiting:                      # the pedal is the player's "go"
                await self.approve(via='pedal')
            self.takes += 1
            self.say(state='listening', mood='concentrating', target='input', take_id=self.take_id(),
                     cue=DRILL_CUE if self.phase == 'drill' else None, drill_card=self.feed.frame['drill_card'])
        elif old == 'recording':                   # a take just finished
            if self.phase == 'drill':
                await self.compare()
            else:
                await self.diagnose()

    async def on_decision(self, msg: dict) -> None:
        if not self.awaiting or msg.get('approval_id') != self.awaiting:
            return
        if msg['type'] == 'coach.approve':
            await self.approve(via='dashboard')
        else:
            self.awaiting = None
            self.phase = 'first'
            await self.until_quiet()
            self.say(state='idle', mood='neutral', target='player', cue=DECLINE_CUE, awaiting_approval=None,
                     drill_card=None, activity=_act(self.feed, 'coach', 'rig_control bypass', 'failed'))

    # ---- script ---------------------------------------------------------
    async def diagnose(self) -> None:
        f = self.feed
        self.say(state='thinking', mood='curious', target='loop', cue=None, before_after=None, drill_card=None,
                 todos=_todos(0), activity=[dict(who='ears', what='get_take_report', status='running')])
        await self.wait(1.4)
        self.say(target='hand', mood='concentrating', todos=_todos(1),
                 activity=_act(f, 'ears', 'get_take_report', 'done') + [dict(who='eyes', what='get_hand_report', status='running')])
        await self.wait(1.6)
        self.say(mood='aha', todos=_todos(2),
                 activity=_act(f, 'eyes', 'get_hand_report', 'done') + [dict(who='coach', what=f'open skill {SKILL}', status='running')])
        await self.wait(0.9)
        card = dict(skill=SKILL, title='Keep the hand moving', passage='G to C change, bars 2-3', reps=4,
                    pass_rule='longest gap under 150 ms', rig=dict(bypass=True),
                    journal_path=f'/journal/scripted/{self.take_id()}.md')
        self.say(state='speaking', mood='concerned', target='player', cue=TAKE_CUE, drill_card=card, todos=_todos(3),
                 activity=_act(f, 'coach', f'open skill {SKILL}', 'done') + [dict(who='coach', what='write_drill_card', status='done')])
        await self.until_quiet()
        self.awaiting = f'a{self.takes}'
        actions = [] if self.bypass else [dict(control='bypass')]
        self.say(state='pointing', mood='encouraging', target='bypass', cue=APPROVE_CUE,
                 awaiting_approval=dict(id=self.awaiting, summary='Effects off so you hear your timing dry.',
                                        actions=actions or [dict(control='bypass')], expires_unix_ms=now_ms() + 60_000),
                 activity=_act(f, 'coach', 'rig_control bypass', 'waiting'))
        asyncio.ensure_future(self._expire(self.awaiting))

    async def _expire(self, approval_id: str) -> None:
        await asyncio.sleep(60)                   # real time, never paced: the player needs the full minute
        if self.awaiting == approval_id:
            await self.on_decision(dict(type='coach.reject', approval_id=approval_id))

    async def approve(self, via: str) -> None:
        self.awaiting = None
        self.phase = 'drill'
        if not self.bypass and self.sender is not None:
            self.sender.send('bypass')
            self.we_bypassed = True
            await self.wait(0.7)                   # let the player see Riff press it before moving on
        self.say(state='listening', mood='concentrating', target='loop', awaiting_approval=None,
                 todos=_todos(4), activity=_act(self.feed, 'coach', 'rig_control bypass', 'done'))
        await self.until_quiet()
        self.say(cue=DRILL_CUE)

    async def compare(self) -> None:
        f = self.feed
        await self.until_quiet()
        self.say(state='thinking', mood='curious', target='loop', cue=None,
                 todos=_todos(4, [dict(text='Compare with last take', status='in_progress')]),
                 activity=_act(f, 'coach', 'compare_takes', 'running'))
        await self.wait(1.5)
        if self.we_bypassed and self.sender is not None:
            self.sender.send('bypass')             # give the player their sound back
            self.we_bypassed = False
        self.say(state='pleased', mood='proud', target='player', cue=PASS_CUE, drill_card=None,
                 todos=_todos(4, [dict(text='Compare with last take', status='completed')]),
                 before_after=dict(before_take_id=f'take-scripted-{self.takes - 1}', after_take_id=self.take_id(),
                                   hesitations=[3, 0], worst_gap_ms=[430, 120], tempo_stability=[0.71, 0.93],
                                   improved=True),
                 activity=_act(f, 'coach', 'compare_takes', 'done') + [dict(who='coach', what='edit /memories/player.md', status='done')])
        self.phase = 'first'
        await self.until_quiet()
        await self.wait(5.0)
        if self.loop != 'recording':
            self.say(state='idle', mood='neutral', target='player', cue=AGAIN_CUE)


async def run_scripted_coach(port: int = 47803, engine_ws: str = 'ws://127.0.0.1:47801', udp_port: int | None = 47800,
                             pace: float = 1.0, speak=None, states=None, ready=None, voice=None) -> None:
    """Serve the scripted session until cancelled. `states` overrides the engine feed (tests).
    `voice` (coach.voice.Voice) speaks each new cue as coach.audio; no voice means the browser's."""
    feed = CoachFeed()
    sender = Sender('coach', port=udp_port) if udp_port else None
    session = ScriptedSession(feed, sender, pace=pace, speak=speak)
    if voice is not None and speak is None:
        async def _speak(text: str) -> None:
            msg = await voice.render(text)
            if msg and feed.frame.get('cue') == text:   # don't play a cue that's already been replaced
                session.heard(text, len(msg['audio_b64']) * 3 / 4 * 8 / 128_000)
                feed._broadcast(msg)
        session.speak = lambda text: asyncio.ensure_future(_speak(text))
    server = asyncio.create_task(feed.serve(port, ready=ready))

    async def follow():
        async for st in (states if states is not None else engine_states(engine_ws)):
            await session.on_state(st)

    async def decide():
        while True:
            await session.on_decision(await feed.decisions.get())

    tasks = [server, asyncio.create_task(follow()), asyncio.create_task(decide())]
    try:
        await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            t.cancel()
        if sender is not None:
            sender.close()
