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
import re
import time
from pathlib import Path

from jsonschema import Draft202012Validator

from .events import Sender

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = Draft202012Validator(json.loads((ROOT / 'protocol/coach.schema.json').read_text()))

SKILL = 'keep-the-hand-moving'
# Riff's voice: a laid-back session player who teaches (BRAND_SPEC.md section 7, "Riff's voice").
TAKE_CUE = "Ooh, close. Your strumming hand stops right at the G to C change. Keep it swinging, even if you miss a string."
APPROVE_CUE = "I'll take the effects off after you approve. Hold the pedal or press Y, then tap to clear and tap again to record."
DRILL_CUE = 'Just the change, four times, no rush. Let the hand keep moving.'
PASS_CUE = "Nice. That gap went from almost half a second to about a tenth. Clear the loop, then record the full pattern as a fresh take."
WRAP_CUE = "That's the session. Your change went from half a second to about a tenth; next time let's push the tempo to 100."
WRAP_SUMMARY = 'G to C change: longest gap 430 to 110 ms. Next: push the tempo to 100 bpm.'
NEXT_TIME = 'Push the tempo to 100 bpm'
MARK_AT = (0.55, 0.66)   # where in the loop the scripted stall is, as a fraction of its length
PLAY_CUE = "Free play. I'll stay quiet. Press Y for another round."
ROUND_CUE = "Okay, what are we working on? Hold V and tell me, or just play it."
DECLINE_CUE = "All good, I'll leave your sound as it is."
IDLE_CUE = "Hey, I'm Riff. What are you working on? Hold V and tell me, then play it for me."
GOAL_CUE = "Got it, that's what we'll work on. Tap the pedal, play it for me, tap again."
NOTED_CUE = "Got it, I'll keep that in mind."
AGAIN_CUE = 'Want to run it again? Hold the pedal or press Y.'
PAUSE_S = 0.9   # a beat of silence after Riff finishes a line, before the next thing happens
WORDS_PER_S = 2.6
TODOS = ['Check timing (ears)', 'Check strumming hand (eyes)', 'Pick one drill', 'Set up the rig']


def now_ms() -> int:
    return int(time.time() * 1000)


class CoachFeed:
    """Holds the latest coach.frame, serves it to every client, and queues decisions from them."""

    def __init__(self, session_id: str = 'scripted'):
        # starts in free play: Riff is drowsy and silent until the player holds the pedal (Y here) or talks to it
        self.frame = dict(version=1, type='coach.frame', timestamp_ms=now_ms(), session_id=session_id,
                          take_id=None, state='idle', mood='sleepy', target='player', cue=None,
                          todos=[], drill_card=None, before_after=None,
                          awaiting_approval=dict(id='again', summary='Start a practice round', actions=[dict(control='loop')],
                                                 expires_unix_ms=now_ms() + 24 * 3600_000),
                          activity=[], scripted=True,
                          session=dict(mode='play', goal=None, plan=[], drill=None, attempt=None, metric=None,
                                       next=None, last_time=None, summary=None, next_time=None))
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
                if SCHEMA.is_valid(msg) and msg.get('type') in ('coach.approve', 'coach.reject', 'coach.say'):
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


def goal_from(text: str) -> str:
    """The player's own words as a goal line: drop a leading 'oh, Riff,' and keep it to 80 characters."""
    t = ' '.join(text.split())
    t = re.sub(r'^(?:(?:oh|hey|ok(?:ay)?|so|um+|uh+|well|riff)[\s,.!]+)+', '', t, flags=re.I).strip() or t
    t = t[0].upper() + t[1:]
    return t if len(t) <= 80 else t[:79].rsplit(' ', 1)[0] + '…'


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
        self.phase = 'play'       # play (free play) until a round starts; then first take, or 'drill' take after approval
        self.awaiting = 'again'   # free play: Y (a long pedal press on the real rig) starts a round
        self.takes = 0
        self.quiet_at = 0.0       # loop time when the current line (plus a pause) is done
        self.history: list[float] = []   # scripted 'longest gap' per take, oldest first
        self.drill_step = 1
        self.mode = 'play'
        self.tries = 0            # tries on the current drill (3 max)
        self.awaiting_kind = 'again'  # 'drill' (the pedal is yes) or 'again' (Y only: PLAY mode keeps the pedal for looping)
        self.last_time = None
        self.summary = None
        self.cue_at = 0.0
        self.loop_seconds = 0.0
        self.goal = None          # the player's own words, if they told Riff what they're working on

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
        self.loop_seconds = float((st.get('loop') or {}).get('seconds') or self.loop_seconds)
        new = (st.get('loop') or {}).get('state', 'idle')
        old, self.loop = self.loop, new
        if old == 'offline':                        # the engine is back: free play stays quiet, a round in progress greets
            if self.mode == 'play':
                self.say(state='idle', mood='sleepy', target='player', cue=None)
            else:
                self.say(state='idle', mood='neutral', target='player', cue=IDLE_CUE)
        if new == old:
            return
        if self.mode == 'play':                    # free play: the pedal is the looper; Riff stays quiet
            return
        if new == 'recording':
            if self.awaiting and self.awaiting_kind == 'drill':   # the pedal is the player's "go"
                await self.approve(via='pedal')
            self.takes += 1
            if self.phase in ('drill1', 'drill2'):
                self.tries += 1
            self.say(state='listening', mood='concentrating', target='input', take_id=self.take_id(), mark=None,
                     session=self.session() if self.phase != 'first' else self.feed.frame.get('session'))
        elif old == 'recording':                   # a take just finished
            if self.phase == 'drill1':
                await self.check_drill1()
            elif self.phase == 'drill2':
                await self.check_drill2()
            else:
                await self.diagnose()

    async def on_say(self, text: str) -> None:
        """The player told Riff something (coach.say). Before the first take it is the goal."""
        if self.loop == 'recording':               # never while playing
            return
        if self.mode == 'play':                    # from free play: a new round with this goal
            await self.new_round(cue=False)
        note = [dict(who='coach', what='write /journal/scripted/goal.md', status='done')]
        if self.phase == 'first' and not self.history:
            self.goal = goal_from(text)
            await self.until_quiet()
            self.say(state='speaking', mood='encouraging', target='player', cue=GOAL_CUE, awaiting_approval=None,
                     session=dict(mode='practice', goal=self.goal, plan=[], drill=None, attempt=None, metric=None,
                                  next=None, last_time=self.last_time, summary=None, next_time=None),
                     activity=_act(self.feed, 'coach', note[0]['what'], 'done'))
        else:
            await self.until_quiet()
            self.say(state='speaking', mood='encouraging', target='player', cue=NOTED_CUE,
                     activity=_act(self.feed, 'coach', 'write /journal/scripted/notes.md', 'done'))

    async def on_decision(self, msg: dict) -> None:
        if msg.get('type') == 'coach.say':
            await self.on_say(msg['text'])
            return
        if not self.awaiting or msg.get('approval_id') != self.awaiting:
            return
        kind = self.awaiting_kind
        if msg['type'] == 'coach.approve':
            if kind == 'again':
                await self.new_round()
            else:
                await self.approve(via='dashboard')
        elif kind == 'drill':
            self.awaiting = self.awaiting_kind = None
            self.phase = 'first'
            await self.until_quiet()
            self.say(state='idle', mood='neutral', target='player', cue=DECLINE_CUE, awaiting_approval=None,
                     drill_card=None, activity=_act(self.feed, 'coach', 'rig_control bypass', 'failed'))

    # ---- the session (ROADMAP §1 "How you use it") ------------------------
    def session(self, attempt: int | None = None) -> dict:
        """The practice session as the player sees it (coach.schema.json `session`). Scripted numbers."""
        drills = [('Keep the hand moving', SKILL), ('Full pattern, fresh take', 'slow-then-speed-up')]
        done = self.drill_step > 2
        step = min(self.drill_step, 2)
        title, skill = drills[step - 1]
        plan = [dict(title=t, status='done' if i + 1 < self.drill_step else 'now' if i + 1 == self.drill_step else 'next')
                for i, (t, _) in enumerate(drills)]
        return dict(mode=self.mode, goal=self.goal or 'Clean G to C change', plan=plan,
                    drill=None if done else dict(title=title, skill=skill, step=step, of=2),
                    attempt=None if done else dict(n=self.tries if attempt is None else attempt, of=3),
                    metric=dict(name='longest gap', unit='ms', target=150, lower_is_better=True, history=self.history[-12:]),
                    next=None if done else ('Full pattern, fresh take' if step == 1 else 'Wrap up'),
                    last_time=self.last_time, summary=self.summary, next_time=NEXT_TIME if self.summary else None)

    async def diagnose(self) -> None:
        """Step 1-2: the first take sets the goal; drill 1 is proposed."""
        f = self.feed
        # Riff's work is paced to be watched (SM review 4): ~10 s, longer than one loop playback
        self.say(state='thinking', mood='curious', target='loop', cue=None, before_after=None, drill_card=None,
                 todos=_todos(0), activity=[dict(who='ears', what='get_take_report', status='running')])
        await self.wait(2.6)
        self.say(target='hand', mood='concentrating', todos=_todos(1),
                 activity=_act(f, 'ears', 'get_take_report', 'done') + [dict(who='eyes', what='get_hand_report', status='running')])
        await self.wait(2.6)
        self.say(target='loop', mood='curious',
                 activity=_act(f, 'eyes', 'get_hand_report', 'done') + [dict(who='coach', what='read_file /memories/player.md', status='running')])
        await self.wait(1.8)
        self.say(mood='aha', todos=_todos(2),
                 activity=_act(f, 'coach', 'read_file /memories/player.md', 'done') + [dict(who='coach', what=f'open skill {SKILL}', status='running')])
        await self.wait(2.0)
        self.say(activity=_act(f, 'coach', f'open skill {SKILL}', 'done') + [dict(who='coach', what='write_drill_card', status='running')])
        await self.wait(1.2)
        card = dict(skill=SKILL, title='Keep the hand moving', passage='G to C change, bars 2-3', reps=4,
                    pass_rule='longest gap under 150 ms', rig=dict(bypass=True),
                    journal_path=f'/journal/scripted/{self.take_id()}.md')
        self.history.append(430.0)
        self.drill_step, self.tries, self.summary = 1, 0, None
        secs = self.loop_seconds or 4.0           # Riff points at the stall in the loop while it names it
        mark = dict(start_s=round(secs * MARK_AT[0], 2), end_s=round(secs * MARK_AT[1], 2), label='430 ms gap')
        self.say(state='pointing', mood='concerned', target='loop', mark=mark, cue=TAKE_CUE, drill_card=card, todos=_todos(3),
                 session=self.session(0),
                 activity=_act(f, 'coach', 'write_drill_card', 'done'))
        await self.until_quiet()
        self.awaiting, self.awaiting_kind = f'a{self.takes}', 'drill'
        self.say(state='pointing', mood='encouraging', target='bypass', cue=APPROVE_CUE, mark=None,
                 awaiting_approval=dict(id=self.awaiting, summary='Effects off so you hear your timing dry.',
                                        actions=[dict(control='bypass')], expires_unix_ms=now_ms() + 60_000),
                 activity=_act(f, 'coach', 'rig_control bypass', 'waiting'))
        asyncio.ensure_future(self._expire(self.awaiting))

    async def _expire(self, approval_id: str) -> None:
        await asyncio.sleep(60)                   # real time, never paced: the player needs the full minute
        if self.awaiting == approval_id and self.awaiting_kind == 'drill':
            await self.on_decision(dict(type='coach.reject', approval_id=approval_id))

    async def approve(self, via: str) -> None:
        """Step 3: the player said yes (pedal or Y). Set up the rig, then the drill take."""
        self.awaiting = self.awaiting_kind = None
        self.phase = 'drill1'
        if not self.bypass and self.sender is not None:
            self.sender.send('bypass')
            self.we_bypassed = True
            await self.wait(0.7)                   # let the player see Riff press it before moving on
        self.say(awaiting_approval=None, todos=_todos(4), activity=_act(self.feed, 'coach', 'rig_control bypass', 'done'),
                 session=self.session(max(self.tries, 1)))
        await self.until_quiet()                   # never walk away mid-sentence
        self.say(state='listening', mood='concentrating', target='loop', cue=DRILL_CUE)

    async def _thinking(self, label: str) -> None:
        await self.until_quiet()
        self.say(state='thinking', mood='curious', target='loop', cue=None,
                 todos=_todos(4, [dict(text=label, status='in_progress')]),
                 activity=_act(self.feed, 'ears', 'get_take_report', 'running'))
        await self.wait(2.4)
        self.say(activity=_act(self.feed, 'ears', 'get_take_report', 'done') + [dict(who='coach', what='compare_takes', status='running')])
        await self.wait(2.2)
        if self.we_bypassed and self.sender is not None:
            self.sender.send('bypass')             # give the player their sound back
            self.we_bypassed = False

    async def check_drill1(self) -> None:
        """Step 4: drill 1 passes; drill 2 asks for a fresh full-pattern take."""
        await self._thinking('Compare with last take')
        self.history.append(120.0)
        self.drill_step, self.tries = 2, 0
        self.phase = 'drill2'
        self.say(state='pleased', mood='proud', target='player', cue=PASS_CUE, drill_card=None,
                 session=self.session(0),
                 todos=_todos(4, [dict(text='Compare with last take', status='completed')]),
                 before_after=dict(before_take_id=f'take-scripted-{self.takes - 1}', after_take_id=self.take_id(),
                                   hesitations=[3, 0], worst_gap_ms=[430, 120], tempo_stability=[0.71, 0.93], improved=True),
                 activity=_act(self.feed, 'coach', 'compare_takes', 'done'))
        await self.until_quiet()
        if self.loop != 'recording':
            self.say(state='idle', mood='neutral', target='loop')

    async def check_drill2(self) -> None:
        """Steps 5-7: drill 2 passes; wrap-up into memory; back to PLAY."""
        await self._thinking('Check the full pattern')
        self.history.append(110.0)
        self.drill_step, self.tries = 3, 0
        self.summary = WRAP_SUMMARY
        self.say(state='pleased', mood='proud', target='player', cue=WRAP_CUE, drill_card=None,
                 session=self.session(),
                 todos=[dict(text='Check the full pattern', status='completed'), dict(text='Write the wrap-up to memory', status='completed')],
                 before_after=dict(before_take_id=f'take-scripted-{self.takes - 1}', after_take_id=self.take_id(),
                                   hesitations=[0, 0], worst_gap_ms=[120, 110], tempo_stability=[0.93, 0.95], improved=True),
                 activity=_act(self.feed, 'coach', 'compare_takes', 'done') + [dict(who='coach', what='edit /memories/player.md', status='done')])
        await self.until_quiet()
        await self.wait(2.0)
        self.mode, self.phase, self.last_time = 'play', 'play', 'the G to C change. Gap down to 110 ms; next, tempo 100.'
        self.awaiting, self.awaiting_kind = 'again', 'again'
        self.say(state='idle', mood='neutral', target='player', cue=PLAY_CUE, todos=[], before_after=None,
                 session=self.session(),
                 awaiting_approval=dict(id='again', summary='Another practice round', actions=[dict(control='loop')],
                                        expires_unix_ms=now_ms() + 24 * 3600_000))

    async def new_round(self, cue: bool = True) -> None:
        """Y in PLAY mode (a long pedal press on the real rig): start another practice session."""
        self.awaiting = self.awaiting_kind = None
        self.mode, self.phase = 'practice', 'first'
        self.history, self.drill_step, self.tries, self.summary, self.goal = [], 1, 0, None, None
        if not cue:
            return
        self.say(state='idle', mood='encouraging', target='player', cue=ROUND_CUE, awaiting_approval=None,
                 session=None, todos=[], before_after=None)


async def run_scripted_coach(port: int = 47803, engine_ws: str = 'ws://127.0.0.1:47801', udp_port: int | None = 47800,
                             pace: float = 1.0, speak=None, states=None, ready=None, voice=None, start_round: bool = False) -> None:
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

        async def _prewarm() -> None:                # render every scripted line once, so no line waits on the network
            for name in ('IDLE_CUE', 'GOAL_CUE', 'NOTED_CUE', 'TAKE_CUE', 'APPROVE_CUE', 'DRILL_CUE', 'PASS_CUE', 'WRAP_CUE', 'PLAY_CUE', 'ROUND_CUE', 'DECLINE_CUE'):
                try:
                    await asyncio.to_thread(voice.synthesize, globals()[name])
                except Exception:
                    pass
        asyncio.ensure_future(_prewarm())
    server = asyncio.create_task(feed.serve(port, ready=ready))

    async def follow():
        async for st in (states if states is not None else engine_states(engine_ws)):
            await session.on_state(st)

    async def decide():
        while True:
            await session.on_decision(await feed.decisions.get())

    async def begin():                               # --coach-round: skip the long press, start practising (demos and layout checks)
        await asyncio.sleep(0.5)
        await session.new_round()

    tasks = [server, asyncio.create_task(follow()), asyncio.create_task(decide())]
    if start_round:
        tasks.append(asyncio.create_task(begin()))
    try:
        await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            t.cancel()
        if sender is not None:
            sender.close()
