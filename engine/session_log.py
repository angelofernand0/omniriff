"""Opt-in JSONL session log: python -m engine --session-log runs/session.jsonl

Records every control the router accepted, plus engine state snapshots at a
low rate, so a demo or practice run can be reviewed or analyzed later (e.g.
by the coach). It never touches the audio callback and never records audio
samples. Lines:

  {"t": <unix ms>, "kind": "start", "argv": [...]}
  {"t": <unix ms>, "kind": "control", "event": <accepted v1 envelope>}
  {"t": <unix ms>, "kind": "state", "state": <state frame, as published on WS>}
  {"t": <unix ms>, "kind": "stop"}

Accepted controls are captured by wrapping router.ingest (the router and
runtime code are unchanged) and queued thread-safely. One asyncio task does
all the file writes.
"""
from __future__ import annotations

import asyncio
import json
import queue
import sys
import time
from pathlib import Path


def _now_ms() -> int:
    return int(time.time() * 1000)


class SessionLog:
    def __init__(self, path, state_hz: float = 2.0):
        self.path = Path(path)
        self.state_period = 1.0 / state_hz if state_hz > 0 else None
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._file = None
        self.runtime = None
        self.lines = 0

    def attach(self, runtime, argv=None) -> "SessionLog":
        """Start logging `runtime` (an engine.runtime.Runtime)."""
        if self.path.exists():
            raise FileExistsError(f"refusing to overwrite {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding="utf-8")
        self.runtime = runtime
        router = runtime.router
        original = router.ingest

        def ingest(raw, *args, **kwargs):
            accepted = original(raw, *args, **kwargs)
            if accepted:
                try:
                    event = json.loads(raw)
                except (ValueError, TypeError):
                    event = None
                self._queue.put({"t": _now_ms(), "kind": "control", "event": event})
            return accepted

        router.ingest = ingest
        self._write({"t": _now_ms(), "kind": "start", "argv": list(argv) if argv is not None else sys.argv[1:]})
        return self

    def _write(self, record: dict) -> None:
        self._file.write(json.dumps(record, allow_nan=False) + "\n")
        self.lines += 1

    def flush_queue(self) -> None:
        while True:
            try:
                self._write(self._queue.get_nowait())
            except queue.Empty:
                break
        self._file.flush()

    def snapshot(self) -> None:
        self._write({"t": _now_ms(), "kind": "state", "state": self.runtime.snapshot()})

    async def run(self) -> None:
        """Write queued controls every 0.25 s and a state snapshot at state_hz until cancelled."""
        next_state = time.monotonic()
        try:
            while True:
                self.flush_queue()
                if self.state_period and time.monotonic() >= next_state:
                    self.snapshot()
                    next_state += self.state_period
                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            pass

    def close(self) -> None:
        if self._file is None:
            return
        self.flush_queue()
        if self.runtime is not None:
            self.snapshot()
        self._write({"t": _now_ms(), "kind": "stop"})
        self._file.close()
        self._file = None
