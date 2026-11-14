"""WAV helpers (stdlib `wave`, PCM only) and a synthetic test signal."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def read_wav(path) -> tuple[np.ndarray, int]:
    """Return (frames x channels float32 in [-1, 1], samplerate)."""
    try:
        with wave.open(str(path), "rb") as w:
            nch, width, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
    except wave.Error as exc:
        raise ValueError(f"{path}: {exc}. Export as 16- or 24-bit PCM WAV.") from exc
    if width == 1:
        data = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        i = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        i = np.where(i & 0x800000, i - 0x1000000, i)
        data = i.astype(np.float32) / 8388608.0
    elif width == 4:
        data = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"{path}: unsupported sample width {width}")
    return data.reshape(-1, nch), sr


def write_wav(path, data: np.ndarray, samplerate: int) -> None:
    """Write float data (frames or frames x channels) as 16-bit PCM."""
    data = np.asarray(data, dtype=np.float32)
    if data.ndim == 1:
        data = data[:, None]
    ints = (np.clip(data, -1.0, 1.0) * 32767.0).round().astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(ints.tobytes())


def make_test_signal(seconds: float = 6.0, samplerate: int = 48000) -> np.ndarray:
    """A bright, guitar-like strummed E5 chord, restruck every second.

    Synthetic test material only, not a recording. Sawtooth partials make a
    low-pass sweep easy to hear.
    """
    t = np.arange(int(seconds * samplerate), dtype=np.float64) / samplerate
    out = np.zeros_like(t)
    for f in (82.41, 123.47, 164.81):
        phase_t = t % 1.0
        env = np.exp(-3.0 * phase_t)
        saw = 2.0 * ((f * t) % 1.0) - 1.0
        out += saw * env
    out *= 0.5 / np.max(np.abs(out))
    return out.astype(np.float32)


def write_test_wav(path, seconds: float = 6.0, samplerate: int = 48000) -> Path:
    write_wav(path, make_test_signal(seconds, samplerate), samplerate)
    return Path(path)
