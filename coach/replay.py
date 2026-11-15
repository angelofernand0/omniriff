"""Opt-in private coach-feed capture and read-only, clearly scripted playback.

This records only validated outbound coach.frame and coach.audio messages. It does
not capture guitar WAVs, microphone input, model prompts, or inbound player words.
The JSONL can still contain private coaching text and MP3s: keep it out of git.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Iterator

from .feed import CoachFeed, VALIDATOR


FORMAT = "omniriff.coach.replay"
VERSION = 1
MAX_LINE = 2_100_000  # coach.audio permits up to 2,000,000 base64 characters
MAX_EVENTS = 20_000
MAX_DURATION_MS = 2 * 60 * 60 * 1000


class ReplayError(ValueError):
    """An invalid or unsafe coach replay file."""


class CoachReplayRecorder:
    """Append complete outbound feed messages to a new, owner-only JSONL file."""

    def __init__(self, path: Path, *, input_provenance: str = "unverified"):
        if input_provenance not in {"unverified", "synthetic_fixture"}:
            raise ValueError("unsupported input provenance")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.path, flags, 0o600)
        self._file = os.fdopen(descriptor, "w", encoding="utf-8")
        self._lock = threading.Lock()
        self._start_ns = time.monotonic_ns()
        self._write({"format": FORMAT, "version": VERSION,
                     "captured_at_ms": int(time.time() * 1000),
                     "input_provenance": input_provenance})

    def _write(self, value: dict) -> None:
        self._file.write(json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n")
        self._file.flush()

    def record(self, message: dict) -> None:
        if message.get("type") not in {"coach.frame", "coach.audio"}:
            raise ValueError("only outbound coach frames and audio may be recorded")
        VALIDATOR.validate(message)
        with self._lock:
            if self._file.closed:
                raise ValueError("replay recorder is closed")
            elapsed_ms = max(0, (time.monotonic_ns() - self._start_ns) // 1_000_000)
            self._write({"at_ms": elapsed_ms, "message": message})

    def close(self) -> None:
        with self._lock:
            self._file.close()


def _lines(path: Path) -> Iterator[dict]:
    with Path(path).open("r", encoding="utf-8") as source:
        line_no = 0
        while True:
            line = source.readline(MAX_LINE + 1)
            if not line:
                return
            line_no += 1
            if len(line) > MAX_LINE or not line.endswith("\n"):
                raise ReplayError(f"replay line {line_no} is too large or incomplete")
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReplayError(f"invalid replay JSON at line {line_no}") from exc
            if not isinstance(value, dict):
                raise ReplayError(f"replay line {line_no} must be an object")
            yield value


def replay_events(path: Path) -> Iterator[dict]:
    """Validate the private recording before it is ever shown to dashboard clients."""
    records = _lines(path)
    header = next(records, None)
    if header is None or set(header) != {"format", "version", "captured_at_ms", "input_provenance"}:
        raise ReplayError("missing coach replay header")
    if (header["format"] != FORMAT or header["version"] != VERSION
            or not isinstance(header["captured_at_ms"], int)
            or header["captured_at_ms"] < 0
            or header["input_provenance"] not in {"unverified", "synthetic_fixture"}):
        raise ReplayError("unsupported coach replay header")
    previous_ms = -1
    count = 0
    for record in records:
        count += 1
        if count > MAX_EVENTS or set(record) != {"at_ms", "message"}:
            raise ReplayError("invalid or excessive replay events")
        at_ms, message = record["at_ms"], record["message"]
        if (type(at_ms) is not int or at_ms < previous_ms or at_ms > MAX_DURATION_MS
                or not isinstance(message, dict)
                or message.get("type") not in {"coach.frame", "coach.audio"}
                or not VALIDATOR.is_valid(message)):
            raise ReplayError(f"invalid coach replay event {count}")
        if count == 1 and message["type"] != "coach.frame":
            raise ReplayError("coach replay must start with a full frame")
        previous_ms = at_ms
        yield record
    if count == 0:
        raise ReplayError("coach replay has no frames")


def play_replay(path: Path, feed: CoachFeed) -> int:
    """Send recorded frames/audio through the normal coach feed at original offsets."""
    if not feed.read_only or not feed.frame["scripted"] or not feed.frame["session_id"].startswith("replay-"):
        raise ValueError("coach replay requires a read-only REPLAY feed")
    # Preflight the whole file so corruption cannot cause a misleading partial show.
    count = sum(1 for _ in replay_events(path))
    start = time.monotonic()
    for event in replay_events(path):
        delay = event["at_ms"] / 1000 - (time.monotonic() - start)
        if delay > 0:
            time.sleep(delay)
        message = event["message"]
        if message["type"] == "coach.frame":
            changes = {key: value for key, value in message.items()
                       if key not in {"version", "type", "timestamp_ms", "session_id", "scripted"}}
            feed.publish(**changes, scripted=True)
        else:
            feed.broadcast_audio({**message, "timestamp_ms": int(time.time() * 1000)})
    return count
