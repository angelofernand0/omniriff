"""Take capture for the practice coach (docs/COACH.md, Piece A).

When the looper finishes recording, a background thread saves the take, the
dry post-gain input exactly as the looper recorded it, to a WAV file plus a
JSON sidecar. The audio callback only bumps counters in the Looper. This
thread polls them, copies the buffer, and discards the copy if a new recording
started meanwhile (the buffer would have been overwritten).

Sidecar fields (take-<stamp>-<n>.json, next to take-<stamp>-<n>.wav):
  version 1, take_id, wav (file name), samplerate, frames, seconds,
  started_unix_ms, ended_unix_ms, source "loop", signal "dry post-gain input
  (pre-effects)", input_gain_db, gate_open_db, seam_fade_ms
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .engine import Engine
from .fileio import write_wav


class TakeWriter:
    def __init__(self, engine: Engine, directory, poll_s: float = 0.02):
        self.engine = engine
        self.directory = Path(directory)
        self.poll_s = poll_s
        self.saved: list[Path] = []
        self.missed = 0
        self._seen = engine.looper.takes_finished
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> "TakeWriter":
        self.directory.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._run, name="omniriff-takes", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(2)
        self.poll()  # catch a take that finished just before stopping

    def _run(self) -> None:
        while not self._stop.wait(self.poll_s):
            self.poll()

    def poll(self) -> Path | None:
        lp = self.engine.looper
        finished = lp.takes_finished
        if finished == self._seen:
            return None
        if finished > self._seen + 1:
            self.missed += finished - self._seen - 1
        self._seen = finished
        generation = lp.take_generation
        length = lp.take_length
        t0, t1 = lp.take_started_ms, lp.take_ended_ms
        if lp.recordings_started != generation or length == 0:
            self.missed += 1  # a new recording already started: the buffer no longer holds this take
            return None
        audio = lp.buf[:length].copy()
        if lp.recordings_started != generation:
            self.missed += 1  # a new recording began while copying
            return None
        return self._write(audio, finished, t0, t1)

    def _write(self, audio, n: int, t0: float, t1: float) -> Path:
        c = self.engine.config
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(t1 / 1000.0))
        take_id = f"take-{stamp}-{n}"
        wav = self.directory / f"{take_id}.wav"
        write_wav(wav, audio, c.samplerate)
        meta = {
            "version": 1, "take_id": take_id, "wav": wav.name, "samplerate": c.samplerate,
            "frames": int(len(audio)), "seconds": round(len(audio) / c.samplerate, 4),
            "started_unix_ms": int(t0), "ended_unix_ms": int(t1), "source": "loop",
            "signal": "dry post-gain input (pre-effects)", "input_gain_db": c.input_gain_db,
            "gate_open_db": c.gate_open_db, "seam_fade_ms": c.loop_fade_ms,
        }
        (self.directory / f"{take_id}.json").write_text(json.dumps(meta, indent=1) + "\n")
        self.saved.append(wav)
        return wav


def write_take(path, audio, samplerate: int, started_unix_ms: float, *, source: str = "record",
               input_gain_db: float = 0.0) -> Path:
    """Write a standalone take (e.g. a plain recording) in the same WAV + sidecar format as TakeWriter."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_wav(path, audio, samplerate)
    meta = {
        "version": 1, "take_id": path.stem, "wav": path.name, "samplerate": samplerate,
        "frames": int(len(audio)), "seconds": round(len(audio) / samplerate, 4),
        "started_unix_ms": int(started_unix_ms), "ended_unix_ms": int(started_unix_ms + 1000.0 * len(audio) / samplerate),
        "source": source, "signal": "dry input (recorded, no effects)", "input_gain_db": input_gain_db,
        "gate_open_db": None, "seam_fade_ms": 0.0,
    }
    path.with_suffix(".json").write_text(json.dumps(meta, indent=1) + "\n")
    return path
