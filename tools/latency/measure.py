"""Pure helpers for latency measurement (no audio device needed)."""
from __future__ import annotations

import statistics
import time

import numpy as np

from audio import Engine, EngineConfig


def click(samplerate: int, ms: float = 1.0, amplitude: float = 0.5) -> np.ndarray:
    """A short, sharp click (half-sine burst) that is easy to find in a recording."""
    n = max(4, int(samplerate * ms / 1000))
    return (amplitude * np.sin(np.linspace(0, np.pi, n))).astype(np.float32)


def find_onsets(recorded: np.ndarray, click_frames: list[int], samplerate: int,
                max_delay_ms: float = 400.0, threshold_ratio: float = 0.3) -> list[int | None]:
    """For each emitted click, find the frame offset of its return in `recorded`.

    The threshold is a fraction of the loudest returned sample, kept well above
    the noise floor measured before the first click. Returns None for clicks
    that never came back within `max_delay_ms`.
    """
    rec = np.abs(np.asarray(recorded, dtype=np.float32))
    if not len(rec) or not click_frames:
        return [None] * len(click_frames)
    first = click_frames[0]
    noise = float(np.percentile(rec[:first], 99.9)) if first > 100 else 0.0
    peak = float(rec.max())
    thr = max(peak * threshold_ratio, noise * 4.0, 1e-4)
    window = int(max_delay_ms / 1000 * samplerate)
    offsets: list[int | None] = []
    for f in click_frames:
        seg = rec[f:f + window]
        hits = np.flatnonzero(seg >= thr)
        offsets.append(int(hits[0]) if len(hits) else None)
    return offsets


def summarize_ms(offsets: list[int | None], samplerate: int) -> dict:
    found = [o * 1000.0 / samplerate for o in offsets if o is not None]
    out = {"clicks": len(offsets), "detected": len(found)}
    if found:
        out.update(
            median_ms=round(statistics.median(found), 2),
            min_ms=round(min(found), 2),
            max_ms=round(max(found), 2),
            stdev_ms=round(statistics.pstdev(found), 2),
        )
    return out


def time_engine(blocksizes=(64, 128, 256), iterations: int = 3000, samplerate: int = 48000) -> list[dict]:
    """Time Engine.process with filter and reverb active. CPU cost only, not I/O latency."""
    rng = np.random.default_rng(0)
    rows = []
    for bs in blocksizes:
        e = Engine(EngineConfig(samplerate=samplerate))
        e.set_filter(0.4)
        e.set_reverb(0.5)
        x = rng.uniform(-0.3, 0.3, bs).astype(np.float32)
        out = np.zeros((bs, 2), np.float32)
        for _ in range(200):
            e.process(x, out)
        times = np.empty(iterations)
        for i in range(iterations):
            t0 = time.perf_counter()
            e.process(x, out)
            times[i] = time.perf_counter() - t0
        ms = times * 1000
        budget = bs / samplerate * 1000
        rows.append({
            "blocksize": bs,
            "budget_ms": round(budget, 3),
            "mean_ms": round(float(ms.mean()), 4),
            "p99_ms": round(float(np.percentile(ms, 99)), 4),
            "max_ms": round(float(ms.max()), 4),
            "load_pct_mean": round(float(ms.mean()) / budget * 100, 1),
        })
    return rows
