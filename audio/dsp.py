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
