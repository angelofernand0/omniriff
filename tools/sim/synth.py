"""Synthetic guitar-like input so the engine meters and looper have real signal.

This is a simulation, not a recording: plucked decaying partials on an eighth-note
grid. Deterministic for a given seed. Output is finite and stays within [-1, 1].
"""
from __future__ import annotations

import numpy as np

# E minor pentatonic, low to mid register (Hz).
NOTES = [82.41, 98.00, 110.00, 123.47, 146.83, 164.81, 196.00, 220.00, 246.94]


class SyntheticGuitar:
    def __init__(self, samplerate: int = 48000, bpm: float = 92.0, seed: int = 7, level: float = 0.28):
        self.sr = samplerate
        self.step = int(samplerate * 60.0 / bpm / 2)  # eighth notes
        self.level = level
        self.rng = np.random.default_rng(seed)
        self.pos = 0
        self.next_pluck = 0
        self.beat = 0
        self.voices: list[list[float]] = []  # [freq, phase, amp, decay_per_sample]

    def _pluck(self) -> None:
        accent = self.beat % 8 == 0
        rest = (self.beat % 8 == 5) or self.rng.random() < 0.12
        self.beat += 1
        if rest:
            return
        freq = float(self.rng.choice(NOTES))
        amp = self.level * (1.75 if accent else self.rng.uniform(0.55, 1.0))
        decay = float(np.exp(-1.0 / (self.sr * self.rng.uniform(0.25, 0.6))))
        self.voices.append([freq, 0.0, amp, decay])
        if len(self.voices) > 6:
            self.voices.pop(0)

    def block(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.float64)
        i = 0
        while i < n:
            if self.pos + i >= self.next_pluck:
                self._pluck()
                self.next_pluck += self.step
            end = min(n, self.next_pluck - self.pos)
            if end <= i:
                end = i + 1
            m = end - i
            idx = np.arange(m)
            for v in self.voices:
                freq, phase, amp, decay = v
                env = amp * decay ** idx
                w = 2 * np.pi * freq / self.sr
                ph = phase + w * idx
                out[i:end] += env * (np.sin(ph) + 0.45 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph)) / 1.65
                v[1] = (phase + w * m) % (2 * np.pi)
                v[2] = amp * decay ** m
            self.voices = [v for v in self.voices if v[2] > 1e-4]
            i = end
        self.pos += n
        np.clip(out, -0.98, 0.98, out=out)
        return out.astype(np.float32)
