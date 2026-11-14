"""Render audio through the engine without any audio device."""
from __future__ import annotations

import math

import numpy as np

from .engine import Engine


def sweep_value(t: float, period: float) -> float:
    """Slow sine sweep between 0 (dark) and 1 (open), starting open."""
    return 0.5 + 0.5 * math.cos(2.0 * math.pi * t / period)


def render(
    engine: Engine,
    mono: np.ndarray,
    blocksize: int = 256,
    out_channels: int = 2,
    sweep_period: float | None = None,
    loop_times: tuple[float, ...] = (),
    on_block=None,
) -> np.ndarray:
    """Process `mono` block by block, applying a scripted sweep and loop toggles."""
    sr = engine.config.samplerate
    n = len(mono)
    out = np.zeros((n, out_channels), dtype=np.float32)
    pending = sorted(loop_times)
    for s in range(0, n, blocksize):
        t = s / sr
        while pending and pending[0] <= t:
            pending.pop(0)
            engine.toggle_loop()
        if sweep_period:
            engine.set_filter(sweep_value(t, sweep_period))
        e = min(n, s + blocksize)
        engine.process(mono[s:e], out[s:e])
        if on_block is not None:
            on_block()
    return out
