"""The pitch riff with a planted feel problem, for testing Ears' swing/attack measures and the real coach.

Four phrases of eight strums (Em, Cmaj7, G, Dsus2), swung eighths at about 100 bpm with even
attacks, except the phrases listed in `straight` (played even, 1:1) and `uneven` (attack loudness
jumping around). This is what docs/PITCH.md's demo story describes: "on the third phrase, swing it
and keep your attacks even". Synthetic: it proves the measurement, not a real player.
"""
from __future__ import annotations

import time

import numpy as np

from tools.virtual_guitar.guitar import CHORDS, _add_strum, _pickup_and_body

SAMPLERATE = 16000
BEAT_S = 0.6
STRUMS_PER_PHRASE = 8


def render_feel_take(*, swing: float = 1.7, straight=(3,), uneven=(3,), seed: int = 11):
    """Audio (float32), samplerate, started_unix_ms, strum times (s)."""
    rng = np.random.default_rng(seed)
    times, velocities, chords = [], [], []
    t = 0.3
    for phrase in range(1, 5):
        ratio = 1.0 if phrase in straight else swing
        long_s, short_s = BEAT_S * ratio / (1 + ratio), BEAT_S / (1 + ratio)
        for k in range(STRUMS_PER_PHRASE):
            times.append(t)
            down = k % 2 == 0
            if phrase in uneven:
                velocities.append(float(rng.uniform(0.15, 1.0)))
            else:
                velocities.append((0.8 if down else 0.62) * float(rng.uniform(0.96, 1.04)))
            chords.append(CHORDS[(phrase - 1) % 4][1])
            t += long_s if down else short_s
    seconds = t + 1.0
    out = np.zeros(int(seconds * SAMPLERATE))
    for when, vel, frets, k in zip(times, velocities, chords, range(len(times))):
        _add_strum(out, when, frets, SAMPLERATE, rng, velocity=vel,
                   direction="down" if k % 2 == 0 else "up", sustain=0.5)
    out = _pickup_and_body(out, SAMPLERATE)
    out = (out * (0.6 / (np.max(np.abs(out)) or 1.0))).astype(np.float32)
    started = int(time.time() * 1000) - round(seconds * 1000)
    return out, SAMPLERATE, started, times
