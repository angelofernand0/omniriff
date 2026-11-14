"""Loopback coach feed: validated full snapshots and local approval decisions."""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator


SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "protocol" / "coach.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


def allowed_origin(origin: str | None) -> bool:
    """Only a loopback web page can approve rig changes via this socket."""
    if origin is None:  # native local test/client with no browser Origin header
        return True
    try:
        parsed = urlsplit(origin)
        return (
            parsed.scheme in {"http", "https"}
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            and parsed.username is None and parsed.password is None
            and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        )
    except ValueError:
        return False


def initial_frame(session_id: str) -> dict:
    frame = {
        "version": 1, "type": "coach.frame", "timestamp_ms": int(time.time() * 1000),
        "session_id": session_id, "take_id": None, "state": "idle",
        "mood": "neutral", "target": None, "cue": None, "todos": [],
        "drill_card": None, "before_after": None, "awaiting_approval": None,
        "activity": [], "scripted": False,
    }
    VALIDATOR.validate(frame)
    return frame


class CoachFeed:
    """Owns one latest coach frame; clients receive the latest full frame on join."""

    def __init__(self, session_id: str, *, host: str = "127.0.0.1", port: int = 47803,
                 scripted: bool = False):
        if host != "127.0.0.1":
            raise ValueError("coach feed must bind only to 127.0.0.1")
        self.host, self.port = host, port
        self.frame = initial_frame(session_id)
        self.frame["scripted"] = bool(scripted)
        self.decisions: queue.Queue[dict] = queue.Queue(maxsize=16)
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server = None
        self._clients: set = set()
        self._ready = threading.Event()
        self._error: Exception | None = None

    def publish(self, **changes) -> dict:
        """Merge changes, validate against the shared schema, and broadcast."""
        with self._lock:
            frame = {**self.frame, **changes, "timestamp_ms": int(time.time() * 1000)}
            VALIDATOR.validate(frame)
            self.frame = frame
            if self._loop is not None:
                asyncio.run_coroutine_threadsafe(self._broadcast(frame), self._loop)
        return frame

    def accept_decision(self, message: dict) -> bool:
        """Validate one dashboard decision; a caller still matches its approval id."""
        if not isinstance(message, dict) or message.get("type") not in {"coach.approve", "coach.reject"}:
            return False
        if not VALIDATOR.is_valid(message):
            return False
        try:
            self.decisions.put_nowait(message)
            return True
        except queue.Full:
            return False

    def publish_activity(self, who: str, what: str, status: str) -> dict:
        """Append a real harness step to the dashboard's bounded activity strip."""
        with self._lock:
            activity = [*self.frame["activity"], {"who": who, "what": what, "status": status}][-8:]
            frame = {**self.frame, "activity": activity, "timestamp_ms": int(time.time() * 1000)}
            VALIDATOR.validate(frame)
            self.frame = frame
            if self._loop is not None:
                asyncio.run_coroutine_threadsafe(self._broadcast(frame), self._loop)
        return frame

    def broadcast_audio(self, message: dict) -> bool:
        """Send validated server-rendered cue audio; never changes frame state."""
        if not isinstance(message, dict) or message.get("type") != "coach.audio" or not VALIDATOR.is_valid(message):
            return False
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._broadcast(message), self._loop)
        return True

    def poll_decision(self, approval_id: str) -> str | None:
        """Discard stale/unrelated decisions and return approve/reject for this id."""
        while True:
            try:
                message = self.decisions.get_nowait()
            except queue.Empty:
                return None
            if message["approval_id"] == approval_id:
                return "approve" if message["type"] == "coach.approve" else "reject"

    async def _broadcast(self, frame: dict) -> None:
        if not self._clients:
            return
        payload = json.dumps(frame, separators=(",", ":"))
        await asyncio.gather(*(client.send(payload) for client in tuple(self._clients)), return_exceptions=True)

    async def _handle(self, websocket) -> None:
        origin = websocket.request.headers.get("Origin")
        if not allowed_origin(origin):
            await websocket.close(code=1008, reason="loopback origin required")
            return
        self._clients.add(websocket)
        try:
            with self._lock:
                frame = self.frame.copy()
            await websocket.send(json.dumps(frame, separators=(",", ":")))
            async for raw in websocket:
                if not isinstance(raw, str) or len(raw) > 2048:
                    continue
                try:
                    self.accept_decision(json.loads(raw))
                except json.JSONDecodeError:
                    continue
        finally:
            self._clients.discard(websocket)

    async def _serve(self) -> None:
        from websockets.asyncio.server import serve

        async with serve(self._handle, self.host, self.port) as server:
            self._server = server
            self.port = server.sockets[0].getsockname()[1]
            self._ready.set()
            await asyncio.Future()

    def start(self) -> "CoachFeed":
        """Start the socket in a daemon thread; no socket is opened at import."""
        if self._thread is not None:
            return self

        def run() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._serve())
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self._error = exc
                self._ready.set()
            finally:
                loop.close()
                self._loop = None

        self._thread = threading.Thread(target=run, name="omniriff-coach-feed", daemon=True)
        self._thread.start()
        if not self._ready.wait(5):
            raise TimeoutError("coach feed did not start")
        if self._error:
            raise RuntimeError("coach feed failed to start") from self._error
        return self

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(lambda: [task.cancel() for task in asyncio.all_tasks()])
        if self._thread is not None:
            self._thread.join(2)
        self._thread = None
