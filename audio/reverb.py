"""Mono Freeverb-style reverb, vectorized per sub-block.

Every delay line is longer than the sub-block, so each block's delayed
samples are already in the buffer from earlier blocks. That lets each comb
and allpass run as a few numpy slice operations instead of a per-sample
Python loop. The damping low-pass inside each comb's feedback path runs on
the delayed block with scipy's lfilter.

Tunings follow the public-domain Freeverb design (Jezar at Dreampoint),
scaled from 44.1 kHz to the engine's samplerate.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import lfilter

COMB_44K = (1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617)
ALLPASS_44K = (556, 441, 341, 225)
INPUT_GAIN = 0.015
ALLPASS_FEEDBACK = 0.5


class _Delay:
    def __init__(self, length: int, max_block: int):
        self.buf = np.zeros(length, np.float32)
        self.length = length
        self.idx = 0
        self.tmp = np.zeros(max_block, np.float32)

    def read(self, n: int) -> np.ndarray:
        """Samples written `length` frames ago, for the next n frames."""
        i, L, out = self.idx, self.length, self.tmp[:n]
        k = min(n, L - i)
        out[:k] = self.buf[i:i + k]
        if k < n:
            out[k:] = self.buf[:n - k]
        return out

    def write(self, x: np.ndarray) -> None:
        n, i, L = len(x), self.idx, self.length
        k = min(n, L - i)
        self.buf[i:i + k] = x[:k]
        if k < n:
            self.buf[:n - k] = x[k:]
        self.idx = (i + n) % L


class Reverb:
    def __init__(self, samplerate: int, max_block: int, room: float = 0.84, damp: float = 0.5):
        scale = samplerate / 44100.0
        self.combs = [_Delay(int(d * scale), max_block) for d in COMB_44K]
        self.allpasses = [_Delay(int(d * scale), max_block) for d in ALLPASS_44K]
        self.min_delay = min(d.length for d in self.combs + self.allpasses)
        self.feedback = room * 0.28 + 0.7
        d = damp * 0.4
        self._b = np.array([1.0 - d])
        self._a = np.array([1.0, -d])
        self._zi = [np.zeros(1) for _ in self.combs]
        self._in = np.zeros(max_block, np.float32)
        self._acc = np.zeros(max_block, np.float32)
        self._tmp = np.zeros(max_block, np.float32)

    def process(self, x: np.ndarray, out: np.ndarray) -> None:
        """Write the wet signal for `x` into `out`. len(x) must be <= min_delay."""
        n = len(x)
        inp = self._in[:n]
        np.multiply(x, INPUT_GAIN, out=inp)
        acc = self._acc[:n]
        acc.fill(0.0)
        tmp = self._tmp[:n]
        for j, comb in enumerate(self.combs):
            delayed = comb.read(n)
            acc += delayed
            damped, self._zi[j] = lfilter(self._b, self._a, delayed, zi=self._zi[j])
            np.multiply(damped, self.feedback, out=tmp)
            tmp += inp
            comb.write(tmp)
        for ap in self.allpasses:
            delayed = ap.read(n)
            np.multiply(delayed, ALLPASS_FEEDBACK, out=tmp)
            tmp += acc
            np.subtract(delayed, acc, out=acc)
            ap.write(tmp)
        out[:n] = acc

    def clear(self) -> None:
        for d in self.combs + self.allpasses:
            d.buf.fill(0.0)
        for z in self._zi:
            z.fill(0.0)
