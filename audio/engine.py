"""OmniRiff real-time audio engine.

Threading model:
- `process()` runs on the audio callback thread. It only reads the latest
  parameter targets, drains a small bounded action queue, and does
  preallocated numpy work. No I/O, logging, locks or blocking calls.
- `submit()` and the `toggle_*`/`set_*` helpers run on any other thread
  (engine/ adapters, CLI keyboard). They never block the callback.
- `snapshot()` can be read from any thread; values are a best-effort view.

Validation of freshness, ordering and duplicates belongs to engine/ (see
protocol/README.md). This class still rejects malformed or low-confidence
events so a bad sender cannot push unsafe values into the DSP.
"""
from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass

import numpy as np

from .dsp import LowPass, NoiseGate, PeakLimiter, Smoother, db_to_gain, filter_cutoff_hz, gain_to_db
from .looper import Looper
from .reverb import Reverb

PARAMETERS = ("filter", "reverb")
ACTIONS = ("loop", "bypass")
ACTION_QUEUE_LIMIT = 32  # pending actions; the callback drains up to 8 per block


@dataclass
class EngineConfig:
    samplerate: int = 48000
    input_gain_db: float = 0.0
    min_confidence: float = 0.6
    smoothing_ms: float = 40.0
    filter_min_hz: float = 120.0
    filter_max_hz: float = 18000.0
    filter_q: float = 0.9
    output_ceiling_db: float = -1.0
    limiter_release_ms: float = 150.0
    gate_open_db: float | None = None   # None = gate off (default); e.g. -50 for single-coil hum
    gate_hysteresis_db: float = 6.0
    input_history_seconds: float = 2.5  # recent dry input kept for the live layer (snapshot_input)
    max_loop_seconds: float = 30.0
    loop_level: float = 1.0
    bypass_fade_ms: float = 10.0
    loop_fade_ms: float = 5.0
    reverb_room: float = 0.84
    reverb_damp: float = 0.5
    reverb_wet_scale: float = 2.0
    subblock: int = 32
    max_block: int = 4096
    meter_decay: float = 0.9


def _is_unit(x) -> bool:
    return (
        isinstance(x, (int, float))
        and not isinstance(x, bool)
        and math.isfinite(x)
        and 0.0 <= x <= 1.0
    )


class Engine:
    def __init__(self, config: EngineConfig | None = None):
        c = self.config = config or EngineConfig()
        sr = c.samplerate
        self._gain = db_to_gain(c.input_gain_db)
        self._ceiling = db_to_gain(c.output_ceiling_db)

        # Latest-value mailbox (float assignment is atomic for readers).
        self._target_filter = 1.0  # fully open: no audible effect until a control moves it
        self._target_reverb = 0.0
        # Unbounded deque, bounded by submit(): a full queue rejects new actions
        # instead of silently dropping the oldest (which would mis-toggle state).
        self._actions: deque[str] = deque()
        self._submit_lock = threading.Lock()

        self._filter_s = Smoother(1.0, c.smoothing_ms, sr, c.subblock)
        self._reverb_s = Smoother(0.0, c.smoothing_ms, sr, c.subblock)
        self._lp = LowPass(sr, c.filter_q)
        self._lp.set_cutoff(filter_cutoff_hz(1.0, c.filter_min_hz, c.filter_max_hz, sr))
        self.looper = Looper(int(c.max_loop_seconds * sr), int(c.loop_fade_ms / 1000 * sr))
        self._reverb = Reverb(sr, c.subblock, c.reverb_room, c.reverb_damp)
        if c.subblock > self._reverb.min_delay:
            raise ValueError("subblock must not exceed the shortest reverb delay")
        self._rv = np.zeros(c.subblock, np.float32)
        # Slightly under the ceiling so float rounding can't reach the safety clip.
        self._gate = (NoiseGate(c.gate_open_db, c.gate_open_db - c.gate_hysteresis_db, sr, c.subblock)
                      if c.gate_open_db is not None else None)
        # Recent dry input (post-gain, pre-gate): the callback copies each block in; readers
        # use snapshot_input(), which is lock-free and retries if the window was overwritten.
        self._hist = np.zeros(max(1, int(c.input_history_seconds * sr)), np.float32)
        self._hist_written = 0  # total frames ever written (int assignment is atomic for readers)
        self._limiter = PeakLimiter(self._ceiling * 0.999, sr, c.subblock, c.limiter_release_ms)

        self._bypass = False
        self._bmix = 0.0  # 0 = effected, 1 = dry
        self._bstep = 1.0 / max(1.0, c.bypass_fade_ms / 1000 * sr)

        m = c.max_block
        self._dry = np.zeros(m, np.float32)
        self._loop = np.zeros(m, np.float32)
        self._mix = np.zeros(m, np.float32)
        self._wet = np.zeros(m, np.float32)
        self._mono = np.zeros(m, np.float32)
        self._ramp = np.zeros(m, np.float32)
        self._idx = np.arange(1, m + 1, dtype=np.float32)

        self._in_peak = 0.0
        self._out_peak = 0.0
        self._xruns = 0
        self._clipped = 0
        self._blocks = 0
        self._accepted = 0
        self._rejected = 0
        self._low_conf = 0

    # ---- control side (any thread except the audio callback) ----

    def submit(self, event) -> bool:
        """Apply one v1 control envelope. Returns True if accepted."""
        try:
            etype = event.get("type")
            control = event.get("control")
        except AttributeError:
            return self._count(rejected=True)
        if etype == "parameter" and control in PARAMETERS:
            value, conf = event.get("value"), event.get("confidence")
            if not (_is_unit(value) and _is_unit(conf)):
                return self._count(rejected=True)
            if conf < self.config.min_confidence:
                return self._count(low_conf=True)
            if control == "filter":
                self._target_filter = float(value)
            else:
                self._target_reverb = float(value)
            return self._count()
        if etype == "action" and control in ACTIONS:
            if "value" in event or "confidence" in event:
                return self._count(rejected=True)
            with self._submit_lock:
                # Only submit() appends, under this lock; the callback only pops,
                # so the length can only shrink between this check and the append.
                full = len(self._actions) >= ACTION_QUEUE_LIMIT
                if not full:
                    self._actions.append(control)
            return self._count(rejected=full)
        return self._count(rejected=True)

    def _count(self, rejected: bool = False, low_conf: bool = False) -> bool:
        with self._submit_lock:
            if rejected:
                self._rejected += 1
            elif low_conf:
                self._low_conf += 1
            else:
                self._accepted += 1
        return not (rejected or low_conf)

    # Local manual controls. Bypass must work even if every sender is down.
    def toggle_bypass(self) -> bool:
        return self.submit({"type": "action", "control": "bypass"})

    def toggle_loop(self) -> bool:
        return self.submit({"type": "action", "control": "loop"})

    def set_filter(self, value: float) -> bool:
        return self.submit({"type": "parameter", "control": "filter", "value": value, "confidence": 1.0})

    def set_reverb(self, value: float) -> bool:
        return self.submit({"type": "parameter", "control": "reverb", "value": value, "confidence": 1.0})

    def note_xrun(self) -> None:
        """Called by the stream wrapper when PortAudio reports an under/overflow."""
        self._xruns += 1

    # ---- audio side (callback thread) ----

    def process(self, inp: np.ndarray, out: np.ndarray) -> None:
        """Process one mono input block into `out` (frames x channels)."""
        n = len(inp)
        m = self.config.max_block
        for s in range(0, n, m):
            e = min(n, s + m)
            self._process_chunk(inp[s:e], out[s:e])

    def _process_chunk(self, inp: np.ndarray, out: np.ndarray) -> None:
        n = len(inp)
        c = self.config
        self._drain_actions()

        dry = self._dry[:n]
        np.multiply(inp, self._gain, out=dry)
        in_peak = float(np.max(np.abs(dry))) if n else 0.0  # pre-gate, so the meter shows the real input
        self._write_history(dry)
        if self._gate is not None:
            self._gate.process(dry)  # before the loop recorder and effects, so hum isn't looped or reverbed

        loop = self._loop[:n]
        self.looper.process(dry, loop)
        mix = self._mix[:n]
        np.multiply(loop, c.loop_level, out=mix)
        np.add(mix, dry, out=mix)

        wet = self._wet[:n]
        sb = c.subblock
        for s in range(0, n, sb):
            e = min(n, s + sb)
            v = self._filter_s.step(self._target_filter)
            self._lp.set_cutoff(filter_cutoff_hz(v, c.filter_min_hz, c.filter_max_hz, c.samplerate))
            self._lp.process(mix[s:e], wet[s:e])
            # Reverb always runs so its tail stays continuous when the amount changes.
            rv_amount = self._reverb_s.step(self._target_reverb)
            rv = self._rv[:e - s]
            self._reverb.process(wet[s:e], rv)
            if rv_amount > 0.0:
                rv *= rv_amount * c.reverb_wet_scale
                wet[s:e] += rv

        # Click-free bypass: per-sample ramp between wet and dry.
        target = 1.0 if self._bypass else 0.0
        r = self._ramp[:n]
        if self._bmix == target:
            r.fill(target)
        else:
            step = self._bstep if target > self._bmix else -self._bstep
            np.multiply(self._idx[:n], step, out=r)
            r += self._bmix
            np.clip(r, 0.0, 1.0, out=r)
            self._bmix = float(r[-1])

        mono = self._mono[:n]
        np.subtract(mix, wet, out=mono)
        mono *= r
        mono += wet

        self._limiter.process(mono)
        out_peak = float(np.max(np.abs(mono))) if n else 0.0
        if out_peak > self._ceiling:  # safety net; the limiter should keep this at zero
            self._clipped += int(np.count_nonzero(np.abs(mono) > self._ceiling))
            np.clip(mono, -self._ceiling, self._ceiling, out=mono)
            out_peak = self._ceiling

        d = c.meter_decay
        self._in_peak = max(in_peak, self._in_peak * d)
        self._out_peak = max(out_peak, self._out_peak * d)
        self._blocks += 1

        out[:n] = mono[:, None]

    def _write_history(self, block: np.ndarray) -> None:
        """Callback-side: copy one block into the history ring (no allocation)."""
        h, n = self._hist, len(block)
        if n >= len(h):
            h[:] = block[-len(h):]
        else:
            i = self._hist_written % len(h)
            k = min(n, len(h) - i)
            h[i:i + k] = block[:k]
            if k < n:
                h[:n - k] = block[k:]
        self._hist_written += n

    def snapshot_input(self, seconds: float | None = None, retries: int = 3):
        """Copy of the most recent dry input, from any non-audio thread.

        Returns (mono float32, frames_written, samplerate). frames_written is the
        engine's running input-frame count at the end of the copy, which lets a
        caller line snapshots up. Lock-free: if the callback wrapped over the
        window while copying, it retries; after `retries` it returns the last copy.
        """
        h = self._hist
        want = len(h) if seconds is None else max(0, min(len(h), int(seconds * self.config.samplerate)))
        out = np.zeros(want, np.float32)
        for _ in range(max(1, retries)):
            end = self._hist_written
            have = min(want, end)
            start = end - have
            i = start % len(h)
            k = min(have, len(h) - i)
            out[want - have:want - have + k] = h[i:i + k]
            if k < have:
                out[want - have + k:] = h[:have - k]
            if self._hist_written - start <= len(h):  # nothing we copied was overwritten
                return out, end, self.config.samplerate
        return out, end, self.config.samplerate

    def _drain_actions(self) -> None:
        for _ in range(8):
            try:
                action = self._actions.popleft()
            except IndexError:
                return
            if action == "bypass":
                self._bypass = not self._bypass
            elif action == "loop":
                self.looper.toggle()

    # ---- state ----

    def snapshot(self) -> dict:
        c = self.config
        lp = self.looper
        return {
            "samplerate": c.samplerate,
            "bypass": self._bypass,
            "loop": {
                "state": lp.state,
                "seconds": lp.length / c.samplerate,
                "max_seconds": c.max_loop_seconds,
            },
            "filter": {
                "target": self._target_filter,
                "value": self._filter_s.value,
                "cutoff_hz": self._lp.cutoff_hz,
            },
            "reverb": {
                "target": self._target_reverb,
                "value": self._reverb_s.value,
                "dsp": True,
            },
            "input_peak_dbfs": gain_to_db(self._in_peak),
            "output_peak_dbfs": gain_to_db(self._out_peak),
            "xruns": self._xruns,
            "clipped_samples": self._clipped,
            "blocks": self._blocks,
            "events": {
                "accepted": self._accepted,
                "rejected": self._rejected,
                "low_confidence": self._low_conf,
            },
        }
