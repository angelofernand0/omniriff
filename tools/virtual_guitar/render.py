"""Render repeatable guitar-like input through the real OmniRiff audio engine."""
from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np

from audio import Engine, EngineConfig
from audio.fileio import make_test_signal
from engine.replay import Replay
from tools.sim.synth import SyntheticGuitar


def load_control_script(path: str | Path) -> list[tuple[int, dict]]:
    """Load a validated replay JSONL file as (offset_ms, event) entries."""
    return Replay.load(path).entries


def synthetic_signal(seconds: float, samplerate: int, bpm: float = 92.0, seed: int = 7,
                     level: float = 0.28, blocksize: int = 256) -> np.ndarray:
    """Return deterministic synthetic guitar-like mono audio.

    ``SyntheticGuitar`` provides note movement and decays. A quieter sawtooth
    chord adds pick-like upper harmonics so low-pass tuning is meaningful; the
    live simulator's three-harmonic plucks alone contain almost no energy above
    3 kHz.
    """
    frames = max(0, int(round(seconds * samplerate)))
    guitar = SyntheticGuitar(samplerate, bpm=bpm, seed=seed, level=level)
    chunks = []
    remaining = frames
    while remaining:
        n = min(blocksize, remaining)
        chunks.append(guitar.block(n))
        remaining -= n
    plucks = np.concatenate(chunks) if chunks else np.zeros(0, np.float32)
    if not frames:
        return plucks
    bright = make_test_signal(seconds, samplerate)[:frames]
    mixed = plucks * 0.82 + bright * level
    np.clip(mixed, -0.98, 0.98, out=mixed)
    return mixed.astype(np.float32)


def _db(value: float) -> float:
    return round(20.0 * math.log10(max(value, 1e-12)), 2)


def signal_metrics(signal: np.ndarray, samplerate: int) -> dict:
    """Return small, deterministic level and spectral metrics for a signal."""
    mono = np.asarray(signal, dtype=np.float32)
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    if not len(mono):
        return {
            "peak_dbfs": -240.0,
            "rms_dbfs": -240.0,
            "crest_db": 0.0,
            "spectral_centroid_hz": 0.0,
            "high_band_energy_pct": 0.0,
        }
    peak = float(np.max(np.abs(mono)))
    rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64))))
    windowed = mono.astype(np.float64) * np.hanning(len(mono))
    power = np.abs(np.fft.rfft(windowed)) ** 2
    freqs = np.fft.rfftfreq(len(mono), 1.0 / samplerate)
    total = float(power.sum())
    centroid = float(np.sum(freqs * power) / total) if total else 0.0
    high = float(power[freqs >= 3000.0].sum() / total * 100.0) if total else 0.0
    return {
        "peak_dbfs": _db(peak),
        "rms_dbfs": _db(rms),
        "crest_db": round(_db(peak) - _db(rms), 2) if rms else 0.0,
        "spectral_centroid_hz": round(centroid, 1),
        "high_band_energy_pct": round(high, 3),
    }


def render_virtual_guitar(
    mono: np.ndarray,
    samplerate: int,
    *,
    controls: list[tuple[int, dict]] | None = None,
    blocksize: int = 128,
    out_channels: int = 2,
    tail_seconds: float = 2.0,
    input_gain_db: float = 0.0,
    filter_value: float = 1.0,
    reverb_value: float = 0.0,
) -> tuple[np.ndarray, dict]:
    """Render audio and controls through ``audio.Engine`` without a sound device.

    Control timestamps are offsets from the start of the render. Events are
    applied at the first block boundary at or after their scheduled offset.
    """
    mono = np.asarray(mono, dtype=np.float32)
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    if mono.ndim != 1:
        raise ValueError("input audio must be mono or frames x channels")
    if samplerate <= 0 or blocksize <= 0 or tail_seconds < 0:
        raise ValueError("samplerate/blocksize must be positive and tail_seconds nonnegative")
    if not np.all(np.isfinite(mono)):
        raise ValueError("input audio contains non-finite samples")

    tail = np.zeros(int(round(tail_seconds * samplerate)), np.float32)
    source = np.concatenate((mono, tail))
    engine = Engine(EngineConfig(samplerate=samplerate, input_gain_db=input_gain_db))
    if not engine.set_filter(filter_value) or not engine.set_reverb(reverb_value):
        raise ValueError("filter_value and reverb_value must be in [0, 1]")

    pending = list(controls or [])
    previous = -1
    for offset, event in pending:
        if offset < previous:
            raise ValueError("control offsets must be nondecreasing")
        previous = offset
        if offset < 0:
            raise ValueError("control offsets must be nonnegative")

    output = np.zeros((len(source), out_channels), np.float32)
    applied = 0
    started = time.perf_counter()
    for start in range(0, len(source), blocksize):
        offset_ms = start * 1000.0 / samplerate
        while applied < len(pending) and pending[applied][0] <= offset_ms:
            if not engine.submit(pending[applied][1]):
                raise ValueError(f"engine rejected control event {applied + 1}")
            applied += 1
        end = min(len(source), start + blocksize)
        engine.process(source[start:end], output[start:end])
    wall_seconds = time.perf_counter() - started

    duration = len(source) / samplerate
    report = {
        "label": "SIMULATED VIRTUAL GUITAR",
        "hardware_latency_measured": False,
        "samplerate": samplerate,
        "blocksize": blocksize,
        "audio_seconds": round(duration, 3),
        "render_wall_seconds": round(wall_seconds, 4),
        "faster_than_realtime": round(duration / wall_seconds, 2) if wall_seconds else None,
        "control_events_scheduled": len(pending),
        "control_events_applied": applied,
        "control_events_unapplied": len(pending) - applied,
        "input": signal_metrics(source, samplerate),
        "output": signal_metrics(output, samplerate),
        "engine": engine.snapshot(),
    }
    return output, report
