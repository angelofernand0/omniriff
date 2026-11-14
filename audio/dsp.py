"""Small DSP building blocks used by the engine. No I/O, no logging."""
from __future__ import annotations

import math

import numpy as np
from scipy.signal import lfilter


def db_to_gain(db: float) -> float:
    return 10.0 ** (db / 20.0)


def gain_to_db(gain: float) -> float:
    return 20.0 * math.log10(max(gain, 1e-9))


def filter_cutoff_hz(value: float, min_hz: float, max_hz: float, samplerate: float) -> float:
    """Map a normalized control value to a low-pass cutoff.

    0 is the darkest setting (min_hz), 1 is fully open (max_hz). The mapping is
    exponential so equal hand movement gives roughly equal perceived change.
    """
    v = min(1.0, max(0.0, float(value)))
    hz = min_hz * (max_hz / min_hz) ** v
    return min(hz, 0.45 * samplerate)


class Smoother:
    """One-pole smoother stepped once per sub-block."""

    def __init__(self, value: float, time_ms: float, samplerate: float, step_frames: int):
        self.value = float(value)
        tau_frames = max(time_ms, 0.0) / 1000.0 * samplerate
        self.coeff = math.exp(-step_frames / tau_frames) if tau_frames > 0 else 0.0

    def step(self, target: float) -> float:
        self.value = target + (self.value - target) * self.coeff
        if abs(self.value - target) < 1e-6:
            self.value = target
        return self.value


class LowPass:
    """RBJ biquad low-pass with state carried across blocks.

    Coefficients are recomputed in place; callers change the cutoff in small,
    smoothed steps so the transposed direct-form state stays well behaved.
    """

    def __init__(self, samplerate: float, q: float):
        self.samplerate = float(samplerate)
        self.q = float(q)
        self.b = np.zeros(3)
        self.a = np.ones(3)
        self.zi = np.zeros(2)
        self.cutoff_hz = 0.0

    def set_cutoff(self, cutoff_hz: float) -> None:
        if cutoff_hz == self.cutoff_hz:
            return
        self.cutoff_hz = cutoff_hz
        w0 = 2.0 * math.pi * cutoff_hz / self.samplerate
        cosw, sinw = math.cos(w0), math.sin(w0)
        alpha = sinw / (2.0 * self.q)
        a0 = 1.0 + alpha
        self.b[0] = (1.0 - cosw) / 2.0 / a0
        self.b[1] = (1.0 - cosw) / a0
        self.b[2] = self.b[0]
        self.a[1] = -2.0 * cosw / a0
        self.a[2] = (1.0 - alpha) / a0

    def process(self, x: np.ndarray, out: np.ndarray) -> None:
        y, self.zi = lfilter(self.b, self.a, x, zi=self.zi)
        out[:] = y


class PeakLimiter:
    """Instant-attack, smooth-release peak limiter, stepped per sub-block.

    For each sub-block, the gain that keeps its peak at the threshold is
    applied at once if it's lower than the current gain (attack). Otherwise
    the gain ramps back toward 1 with a release time constant, never above
    what that sub-block allows. The output therefore never exceeds the
    threshold, and the engine's hard clip becomes a safety net that should
    count zero samples.
    """

    def __init__(self, threshold: float, samplerate: float, step_frames: int, release_ms: float):
        self.threshold = float(threshold)
        self.step = int(step_frames)
        self.gain = 1.0
        tau = max(release_ms, 1e-3) / 1000.0 * samplerate
        self.release = 1.0 - math.exp(-self.step / tau)
        self._lin = np.linspace(0.0, 1.0, self.step + 1, dtype=np.float32)[1:]
        self._abs = np.zeros(self.step, np.float32)
        self._ramp = np.zeros(self.step, np.float32)

    def process(self, x: np.ndarray) -> None:
        """Limit `x` in place."""
        n, st = len(x), self.step
        for s in range(0, n, st):
            seg = x[s:s + st]
            k = len(seg)
            a = self._abs[:k]
            np.abs(seg, out=a)
            peak = float(a.max())
            target = self.threshold / peak if peak > self.threshold else 1.0
            g = self.gain
            if target < g:
                seg *= target
                self.gain = target
            else:
                new = min(target, g + (1.0 - g) * self.release)
                if new != g or g != 1.0:
                    r = self._ramp[:k]
                    np.multiply(self._lin[:k], new - g, out=r)
                    r += g
                    seg *= r
                    self.gain = float(r[-1])


class NoiseGate:
    """Downward gate on the dry input, stepped per sub-block (off unless configured).

    Opens when a sub-block's RMS rises above `open_db`; closes after `hold_ms`
    once RMS falls below `close_db` (hysteresis stops chatter on decaying notes).
    Gain ramps linearly within each sub-block: fast attack, slower release, so
    notes don't click on and tails fade instead of chopping.
    """

    def __init__(self, open_db: float, close_db: float, samplerate: float, step_frames: int,
                 attack_ms: float = 2.0, release_ms: float = 120.0, hold_ms: float = 60.0):
        if close_db > open_db:
            raise ValueError("close_db must be at or below open_db")
        self.open_level = 10 ** (open_db / 20)
        self.close_level = 10 ** (close_db / 20)
        self.step = int(step_frames)
        step_s = self.step / samplerate
        self.attack = min(1.0, step_s / max(attack_ms / 1000.0, 1e-6))
        self.release = min(1.0, step_s / max(release_ms / 1000.0, 1e-6))
        self.hold_steps = int(round(hold_ms / 1000.0 / step_s))
        self.gain = 0.0
        self.is_open = False
        self._hold = 0
        self._lin = np.linspace(0.0, 1.0, self.step + 1, dtype=np.float32)[1:]
        self._ramp = np.zeros(self.step, np.float32)

    def process(self, x: np.ndarray) -> None:
        """Gate `x` in place."""
        n, st = len(x), self.step
        for s in range(0, n, st):
            seg = x[s:s + st]
            k = len(seg)
            rms = float(np.sqrt(np.dot(seg, seg) / k)) if k else 0.0
            if rms >= self.open_level:
                self.is_open, self._hold = True, self.hold_steps
            elif rms < self.close_level and self.is_open:
                if self._hold > 0:
                    self._hold -= 1
                else:
                    self.is_open = False
            target = 1.0 if self.is_open else 0.0
            g = self.gain
            rate = self.attack if target > g else self.release
            new = g + (target - g) * rate if abs(target - g) > 1e-6 else target
            if g == 1.0 and new == 1.0:
                continue
            r = self._ramp[:k]
            np.multiply(self._lin[:k], new - g, out=r)
            r += g
            seg *= r
            self.gain = float(r[-1]) if k else g
