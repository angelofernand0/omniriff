"""Render a before/clean/after coaching sequence without a guitar or camera.

The planted delays and wrist freezes are ground truth for testing Ears/Eyes;
they are not measurements of a player or a real recording.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from audio.fileio import write_wav
from tools.virtual_guitar.guitar import CHORDS, _add_strum, _pickup_and_body


SAMPLERATE = 16000
FPS = 30
START_UNIX_MS = 1_700_000_000_000  # stable synthetic wall-clock origin
FIRST_STRUM_S = 0.35
INTERVAL_S = 0.5
STRUM_COUNT = 16
CHORD_CHANGE_INDICES = (4, 8, 12)
GAPS_MS = {"before": 400, "clean": 0, "after": 120}


def timing(gap_ms: int) -> tuple[list[float], list[tuple[float, float]]]:
    """Return actual strum times and planted stationary-hand windows."""
    if gap_ms < 0:
        raise ValueError("gap_ms must be nonnegative")
    gap_s = gap_ms / 1000.0
    times = []
    stalls = []
    for index in range(STRUM_COUNT):
        preceding_changes = sum(index > change for change in CHORD_CHANGE_INDICES)
        start = FIRST_STRUM_S + index * INTERVAL_S + preceding_changes * gap_s
        if index in CHORD_CHANGE_INDICES:
            if gap_s:
                stalls.append((start, start + gap_s))
            start += gap_s
        times.append(start)
    return times, stalls


def render_audio(strums_s: list[float], samplerate: int = SAMPLERATE) -> np.ndarray:
    """Pick deterministic physical-model chords at the requested times."""
    frames = int(round((strums_s[-1] + 1.0) * samplerate))
    output = np.zeros(frames, dtype=np.float64)
    rng = np.random.default_rng(519)
    for index, when in enumerate(strums_s):
        _, frets = CHORDS[(index // 4) % len(CHORDS)]
        _add_strum(
            output, when, frets, samplerate, rng,
            velocity=0.80 if index % 2 == 0 else 0.63,
            direction="down" if index % 2 == 0 else "up",
            sustain=0.72,
        )
    output = _pickup_and_body(output, samplerate)
    peak = float(np.max(np.abs(output)))
    return (output * (0.55 / peak if peak else 0.0)).astype(np.float32)


def hand_samples(duration_s: float, stalls_s: list[tuple[float, float]]):
    """A moving wrist that freezes mid-stroke during each planted pause."""
    count = int(duration_s * FPS) + 1
    for frame in range(count):
        t = frame / FPS
        frozen_s = sum(max(0.0, min(t, end) - start) for start, end in stalls_s)
        moving_t = t - frozen_s
        y = 0.5 + 0.20 * np.sin(2.0 * np.pi * moving_t)
        yield {
            "timestamp_ms": START_UNIX_MS + round(t * 1000),
            "hands": [{"handedness": "Right", "wrist": [0.52, round(float(y), 5)], "confidence": 0.99}],
        }


def generate(directory: Path, samplerate: int = SAMPLERATE) -> dict:
    """Write WAV, TakeWriter-shaped sidecar, hand JSONL and ground truth."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "source": "synthetic_fixture", "takes": []}
    for name, gap_ms in GAPS_MS.items():
        take_id = f"coach-{name}"
        strums_s, stalls_s = timing(gap_ms)
        audio = render_audio(strums_s, samplerate)
        duration_s = len(audio) / samplerate
        wav = directory / f"{take_id}.wav"
        hand_log = directory / f"{take_id}.hands.jsonl"
        write_wav(wav, audio, samplerate)
        sidecar = {
            "version": 1, "take_id": take_id, "wav": wav.name,
            "samplerate": samplerate, "frames": len(audio),
            "seconds": round(duration_s, 4),
            "started_unix_ms": START_UNIX_MS,
            "ended_unix_ms": START_UNIX_MS + round(duration_s * 1000),
            "source": "synthetic_fixture",
            "signal": "physical-model guitar, dry synthetic input (not a recording)",
            "input_gain_db": 0.0, "gate_open_db": None, "seam_fade_ms": 0.0,
        }
        wav.with_suffix(".json").write_text(json.dumps(sidecar, indent=2) + "\n")
        with hand_log.open("w") as stream:
            for sample in hand_samples(duration_s, stalls_s):
                stream.write(json.dumps(sample, separators=(",", ":")) + "\n")
        manifest["takes"].append({
            "take_id": take_id, "wav": wav.name,
            "sidecar": wav.with_suffix(".json").name,
            "hand_log": hand_log.name,
            "planted_gap_ms": gap_ms,
            "planted_onsets_ms": [round(strums_s[i] * 1000) for i in CHORD_CHANGE_INDICES] if gap_ms else [],
            "planted_stalls_ms": [[round(start * 1000), round(end * 1000)] for start, end in stalls_s],
        })
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "generated")
    args = parser.parse_args()
    manifest = generate(args.out)
    print(f"Wrote {len(manifest['takes'])} synthetic coach takes to {args.out}")


if __name__ == "__main__":
    main()
