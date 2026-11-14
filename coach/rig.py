"""Rig I/O for the separate coach process, never for the audio callback."""
from __future__ import annotations

import copy
import json
import math
import socket
import threading
import time
from pathlib import Path

from jsonschema import Draft202012Validator


CONTROL_SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "protocol" / "control.schema.json").read_text())
CONTROL_VALIDATOR = Draft202012Validator(CONTROL_SCHEMA)
STATE_MAX_AGE_S = 2.0


def control_message(control: str, value: float | None, seq: int, timestamp_ms: int) -> dict:
    """Build and schema-check one coach control envelope."""
    if control not in {"bypass", "filter", "reverb", "loop"}:
        raise ValueError("unknown rig control")
    message = {
        "version": 1, "source": "coach", "seq": seq,
        "timestamp_ms": timestamp_ms,
        "type": "parameter" if control in {"filter", "reverb"} else "action",
        "control": control,
    }
    if message["type"] == "parameter":
        if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("filter/reverb require a finite value")
        message.update(value=float(value), confidence=1.0)
    elif value is not None:
        raise ValueError("action controls must not carry a value")
    CONTROL_VALIDATOR.validate(message)
    return message


class RigClient:
    """Send approved controls to UDP 47800; fixture mode only records them."""

    def __init__(self, *, fixture_mode: bool = False, port: int = 47800):
        self.fixture_mode = fixture_mode
        self.port = port
        self.sent: list[dict] = []
        self._seq = 0

    def send(self, control: str, value: float | None = None) -> dict:
        message = control_message(control, value, self._seq, int(time.time() * 1000))
        self._seq += 1
        if not self.fixture_mode:
            data = json.dumps(message, separators=(",", ":")).encode()
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(data, ("127.0.0.1", self.port))
        self.sent.append(message)
        return message


class RigStateReader:
    """Read the engine's loopback state socket off the audio thread."""

    def __init__(self, *, port: int = 47801):
        self.port = port
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest: dict | None = None
        self._received_at = 0.0
        self._recording_counter = 0
        self._pending_actions: dict[str, object] = {}

    def observe(self, state: dict) -> None:
        """Accept one engine frame; also useful for a no-network runner test."""
        if not isinstance(state, dict):
            return
        loop = state.get("loop")
        current = loop.get("state") if isinstance(loop, dict) else None
        with self._lock:
            old_loop = self._latest.get("loop") if self._latest else None
            old = old_loop.get("state") if isinstance(old_loop, dict) else None
            if current == "recording" and old != "recording":
                self._recording_counter += 1
            self._latest = copy.deepcopy(state)
            self._received_at = time.monotonic()
            for control, desired in tuple(self._pending_actions.items()):
                actual = state.get("bypass") if control == "bypass" else current
                if actual == desired:
                    del self._pending_actions[control]

    def snapshot(self) -> dict:
        with self._lock:
            if self._latest is None or time.monotonic() - self._received_at > STATE_MAX_AGE_S:
                return {"available": False}
            return copy.deepcopy(self._latest)

    def action_pending(self, control: str) -> bool:
        with self._lock:
            return control in self._pending_actions

    def mark_action_pending(self, control: str, desired: object) -> None:
        with self._lock:
            current = self._latest.get("bypass") if control == "bypass" and self._latest else None
            if control == "loop" and self._latest:
                loop = self._latest.get("loop")
                current = loop.get("state") if isinstance(loop, dict) else None
            if current != desired:
                self._pending_actions[control] = desired

    def mark_disconnected(self) -> None:
        with self._lock:
            self._received_at = 0.0

    def recording_counter(self) -> int:
        with self._lock:
            return self._recording_counter

    def start(self) -> "RigStateReader":
        if self._thread is not None:
            return self

        def run() -> None:
            from websockets.sync.client import connect
            from websockets.exceptions import ConnectionClosed

            url = f"ws://127.0.0.1:{self.port}"
            while not self._stop.is_set():
                try:
                    with connect(url, open_timeout=2) as ws:
                        while not self._stop.is_set():
                            try:
                                raw = ws.recv(timeout=1)
                            except TimeoutError:
                                continue
                            except ConnectionClosed:
                                break
                            if isinstance(raw, str) and len(raw) <= 100_000:
                                try:
                                    self.observe(json.loads(raw))
                                except json.JSONDecodeError:
                                    pass
                except (OSError, TimeoutError, ConnectionClosed):
                    self._stop.wait(0.5)
                finally:
                    self.mark_disconnected()

        self._thread = threading.Thread(target=run, name="omniriff-coach-rig-state", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(3)
            self._thread = None
        self.mark_disconnected()
