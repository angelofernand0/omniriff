"""Hosted coach: the real coach, one session per browser, over one WebSocket.

The website (browser instrument: your guitar + webcam) connects to
wss://<host>/coach?player=<id> and must send {"type": "omniriff.hello", "key": <team passcode>}
as its first message within 5 s (the passcode never rides in a URL, so proxy access logs can't
record it; it is compared in constant time). Nothing else, and no model call, happens before that.
A missing Origin header (a native client, e.g. tools/showcase/realrun.py) is allowed: the passcode
still gates it; browsers always send Origin, and only listed page origins are accepted.
Each connection gets the same CoachRunner the local rig uses, with three adapters instead of the
loopback sockets:

  browser -> server  omniriff.hello     first message: the team passcode
                     coach.say / coach.approve / coach.reject   (same as the local dashboard)
                     omniriff.state     the browser looper's state (loop, bypass, filter, reverb)
                     omniriff.practice  Y / pedal hold: start or pause a practice round
                     omniriff.take      a finished loop: 16-bit PCM + the webcam wrist track
  server -> browser  coach.frame / coach.audio                   (same as the local dashboard)
                     omniriff.control   an approved rig change, applied by the browser engine

The API keys stay in this process. A team passcode, a session limit and the shared
budget guard keep strangers from spending credit. Memory is kept per player id under
the data directory, so "Last time..." works across visits on a persistent disk.

    OMNIRIFF_COACH_PASSCODE=... python -m coach.server --port 8787
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hmac
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .feed import CoachFeed
from .rig import RigClient, RigStateReader, control_message

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "coach" / "workspace"
DEFAULT_ORIGINS = (
    "https://omniriff.vercel.app",
    "https://omniriff.courses",
    "https://www.omniriff.courses",
    "http://127.0.0.1:5173", "http://localhost:5173",
    "http://127.0.0.1:4173", "http://localhost:4173",
    "http://127.0.0.1:8080", "http://localhost:8080",
)
PLAYER_ID = re.compile(r"^[a-z0-9][a-z0-9-]{7,63}$")
MAX_TAKE_SECONDS = 32.0
MAX_MESSAGE = 4 * 1024 * 1024        # a 30 s, 16 kHz 16-bit take is ~1.3 MB of base64
MAX_HAND_SAMPLES = 32 * 60           # 32 s at 60 fps
HELLO_TIMEOUT_S = 5.0
LOG = logging.getLogger("coach.server")


class RemoteFeed(CoachFeed):
    """A CoachFeed whose only client is one browser socket on the server's event loop."""

    def __init__(self, session_id: str, websocket, loop: asyncio.AbstractEventLoop):
        super().__init__(session_id, scripted=False)
        self._loop = loop
        self._clients = {websocket}

    def start(self):  # the server already owns the socket
        return self

    def stop(self) -> None:
        self._clients = set()

    def send_raw(self, message: dict) -> None:
        asyncio.run_coroutine_threadsafe(self._broadcast(message), self._loop)


class RemoteRig(RigClient):
    """Approved rig changes go back to the browser, which applies them to its own engine."""

    def __init__(self, feed: RemoteFeed):
        super().__init__(fixture_mode=True)
        self.feed = feed

    def send(self, control: str, value: float | None = None) -> dict:
        message = control_message(control, value, self._seq, int(time.time() * 1000))
        self._seq += 1
        self.sent.append(message)
        self.feed.send_raw({"type": "omniriff.control", "control": control, "value": value})
        return message


def _seed_workspace(workspace: Path) -> Path:
    """Copy the coach's instructions and skills into a player's workspace (memory is kept)."""
    workspace.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATE / "AGENTS.md", workspace / "AGENTS.md")
    shutil.copytree(TEMPLATE / "skills", workspace / "skills", dirs_exist_ok=True)
    (workspace / "memories").mkdir(exist_ok=True)
    example = TEMPLATE / "memories" / "player.example.md"
    if example.exists():
        shutil.copy2(example, workspace / "memories" / "player.example.md")
    return workspace


def _clean_hand(hand: dict) -> dict | None:
    try:
        x, y = (float(v) for v in hand["wrist"])
        conf = float(hand.get("confidence", 0.9))
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= x <= 1 and 0 <= y <= 1 and 0 <= conf <= 1):
        return None
    clean = {"handedness": "Left" if hand.get("handedness") == "Left" else "Right",
             "wrist": [x, y], "confidence": conf}
    points = hand.get("landmarks")
    if isinstance(points, list) and len(points) == 21:
        try:
            pts = [[round(float(a), 4), round(float(b), 4)] for a, b in points]
        except (TypeError, ValueError):
            pts = None
        if pts and all(-0.5 <= v <= 1.5 for pt in pts for v in pt):
            clean["landmarks"] = pts
    return clean


def hand_records(samples: list) -> list[dict]:
    """Browser camera frames -> vision hand-log records (old flat wrist samples are accepted too).

    strum_hand is the hand whose wrist swings most up and down over the take: camera mirroring
    makes MediaPipe's Left/Right label unreliable, the picking motion is not."""
    records = []
    for sample in samples[:MAX_HAND_SAMPLES]:
        if not isinstance(sample, dict):
            continue
        try:
            ts = int(sample["timestamp_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        raw = sample.get("hands") if isinstance(sample.get("hands"), list) else [sample]
        hands = [h for h in (_clean_hand(r) for r in raw[:2] if isinstance(r, dict)) if h]
        if ts > 0 and hands:
            records.append({"timestamp_ms": ts, "hands": hands})
    swing = {}
    for label in ("Left", "Right"):
        ys = [h["wrist"][1] for r in records for h in r["hands"] if h["handedness"] == label]
        if len(ys) > 5:
            mean = sum(ys) / len(ys)
            swing[label] = sum((y - mean) ** 2 for y in ys) / len(ys)
    strum = max(swing, key=swing.get) if swing else "Right"
    for record in records:
        record["strum_hand"] = strum
    return records


class Session:
    """One browser = one coach runner thread."""

    def __init__(self, server: "CoachServer", websocket, player: str):
        self.server = server
        self.id = uuid.uuid4().hex
        self.dir = server.data / "sessions" / self.id
        self.takes = self.dir / "takes"
        self.takes.mkdir(parents=True)
        self.hand_log = self.dir / "hands.jsonl"
        self.hand_log.touch()
        self.workspace = _seed_workspace(server.data / "players" / player / "workspace")
        self.feed = RemoteFeed(self.id, websocket, asyncio.get_running_loop())
        self.state = RigStateReader()           # never started: the browser pushes its state
        self.rig = RemoteRig(self.feed)
        self.stop = threading.Event()
        self.practice_count = 0
        self.take_n = 0
        self._latest_state: dict = {}
        self.thread = threading.Thread(target=self._run, name=f"coach-{self.id[:8]}", daemon=True)

    def _run(self) -> None:
        from .agent import build_agent
        from .runner import CoachRunner
        from .tools import CoachTools
        try:
            service = CoachTools(self.workspace, self.feed, self.rig, self.state)
            self.feed.publish(session=service.session.snapshot())
            if not self.server.budget.allow_new_run():
                self.feed.publish(state="asleep", mood="sleepy", cue="Coach is out of credit.")
                return
            agent = build_agent(service, budget=self.server.budget)
            runner = CoachRunner(agent, service, self.feed, self.state, self.server.budget,
                                 hand_log=self.hand_log, quiet_until_asked=True)
            runner.run_directory(self.takes, stop=self.stop)
        except Exception:
            LOG.exception("session %s stopped", self.id[:8])
            try:
                self.feed.publish(state="asleep", mood="sleepy", target=None,
                                  cue="The coach hit a problem. Your instrument still works.")
            except Exception:
                pass

    def observe(self, message: dict) -> None:
        state = {k: message[k] for k in ("loop", "bypass", "filter", "reverb") if k in message}
        if self.practice_count:
            state["pedal"] = {"practice_count": self.practice_count, "last_practice_ms": int(time.time() * 1000)}
        self._latest_state = state
        self.state.observe(state)

    def practice(self) -> None:
        self.practice_count += 1
        self.observe(self._latest_state or {"loop": {"state": "idle"}})

    def take(self, message: dict) -> str:
        sr = message.get("samplerate")
        started = message.get("started_unix_ms")
        pcm = message.get("pcm16_b64")
        if not isinstance(sr, int) or not 8000 <= sr <= 48000:
            return "bad samplerate"
        if not isinstance(started, (int, float)) or not isinstance(pcm, str):
            return "bad take"
        import numpy as np
        from audio.takes import write_take
        try:
            raw = base64.b64decode(pcm, validate=True)
        except ValueError:
            return "bad audio encoding"
        audio = np.frombuffer(raw[: len(raw) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
        if not 0.5 <= len(audio) / sr <= MAX_TAKE_SECONDS:
            return "take length out of range"
        hands = message.get("hands")
        records = hand_records(hands if isinstance(hands, list) else [])
        if records:
            with self.hand_log.open("a", encoding="utf-8") as stream:
                for record in records:
                    stream.write(json.dumps(record, separators=(",", ":")) + "\n")
        self.take_n += 1
        write_take(self.takes / f"take-{int(started)}-{self.take_n}.wav", audio, sr, started, source="loop")
        return "ok"

    def close(self) -> None:
        self.stop.set()
        self.feed.stop()


class CoachServer:
    def __init__(self, *, passcode: str | None, origins: set[str], data: Path, max_sessions: int):
        from .budget import BudgetGuard
        self.passcode = passcode
        self.origins = origins
        self.data = data
        self.max_sessions = max_sessions
        self.sessions: set[Session] = set()
        self.data.mkdir(parents=True, exist_ok=True)
        self.budget = BudgetGuard(self.data / "usage.jsonl",
                                  limit_usd=float(os.environ.get("OMNIRIFF_COACH_LIMIT_USD", "8")))

    def _reject(self, connection, status: HTTPStatus, text: str):
        return connection.respond(status, text + "\n")

    def process_request(self, connection, request):
        url = urlsplit(request.path)
        if url.path == "/healthz":
            return connection.respond(HTTPStatus.OK, "ok\n")
        if url.path != "/coach":
            return self._reject(connection, HTTPStatus.NOT_FOUND, "not found")
        origin = request.headers.get("Origin")
        if origin is not None and origin not in self.origins:
            return self._reject(connection, HTTPStatus.FORBIDDEN, "origin not allowed")
        query = parse_qs(url.query)
        if not PLAYER_ID.match(query.get("player", [""])[0]):
            return self._reject(connection, HTTPStatus.BAD_REQUEST, "player id required")
        if len(self.sessions) >= self.max_sessions:
            return self._reject(connection, HTTPStatus.SERVICE_UNAVAILABLE, "coach is busy, try again soon")
        return None

    def authorized(self, key: object) -> bool:
        """Constant-time passcode check; no passcode configured = loopback test mode."""
        if not self.passcode:
            return True
        return isinstance(key, str) and hmac.compare_digest(key.encode(), self.passcode.encode())

    async def handle(self, websocket) -> None:
        player = parse_qs(urlsplit(websocket.request.path).query)["player"][0]
        try:
            hello = json.loads(await asyncio.wait_for(websocket.recv(), HELLO_TIMEOUT_S))
        except (asyncio.TimeoutError, json.JSONDecodeError, TypeError, ValueError):
            hello = None
        except Exception:
            return  # the client went away before saying hello
        if not (isinstance(hello, dict) and hello.get("type") == "omniriff.hello" and self.authorized(hello.get("key"))):
            await websocket.close(4401, "wrong passcode")
            return
        if len(self.sessions) >= self.max_sessions:
            await websocket.close(4503, "coach is busy, try again soon")
            return
        session = Session(self, websocket, player)
        self.sessions.add(session)
        LOG.info("session %s open (player %s, %d active)", session.id[:8], player[:8], len(self.sessions))
        try:
            await websocket.send(json.dumps(session.feed.frame, separators=(",", ":")))
            session.thread.start()
            async for raw in websocket:
                if not isinstance(raw, str):
                    continue
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                kind = message.get("type")
                if kind == "coach.say":
                    session.feed.accept_say(message)
                elif kind in ("coach.approve", "coach.reject"):
                    session.feed.accept_decision(message)
                elif kind == "omniriff.state":
                    session.observe(message)
                elif kind == "omniriff.practice":
                    session.practice()
                elif kind == "omniriff.take":
                    result = await asyncio.to_thread(session.take, message)
                    await websocket.send(json.dumps({"type": "omniriff.take_ack", "result": result}))
        finally:
            session.close()
            self.sessions.discard(session)
            LOG.info("session %s closed", session.id[:8])

    async def serve(self, host: str, port: int) -> None:
        from websockets.asyncio.server import serve
        async with serve(self.handle, host, port, process_request=self.process_request,
                         max_size=MAX_MESSAGE, ping_interval=20, ping_timeout=40) as server:
            LOG.info("hosted coach on ws://%s:%d/coach", host, server.sockets[0].getsockname()[1])
            await asyncio.Future()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8787")))
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("OMNIRIFF_COACH_DATA", ROOT / "runs" / "coach-server")))
    parser.add_argument("--max-sessions", type=int, default=int(os.environ.get("OMNIRIFF_COACH_MAX_SESSIONS", "3")))
    parser.add_argument("--no-passcode", action="store_true", help="local testing only: accept any client on loopback")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="coach-server: %(levelname)s %(message)s")
    from .smoke import load_key
    load_key()
    passcode = os.environ.get("OMNIRIFF_COACH_PASSCODE") or None
    if not passcode and not args.no_passcode:
        parser.error("set OMNIRIFF_COACH_PASSCODE (or --no-passcode for a loopback test)")
    if args.no_passcode and args.host not in ("127.0.0.1", "localhost"):
        parser.error("--no-passcode is only allowed on 127.0.0.1")
    extra = {o.strip() for o in os.environ.get("OMNIRIFF_COACH_ORIGINS", "").split(",") if o.strip()}
    server = CoachServer(passcode=passcode, origins=set(DEFAULT_ORIGINS) | extra,
                         data=args.data, max_sessions=args.max_sessions)
    try:
        asyncio.run(server.serve(args.host, args.port))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
