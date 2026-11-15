"""Render one reproducible practice take: the riff in docs/PLAY-THIS.md.

The pattern is the coach fixture's: Em - Cmaj7 - G - Dsus2, one chord per four strums,
down-up at 0.5 s per strum (120 bpm), 16 strums. `gap_ms` is the pause before each chord
change, with the strumming wrist frozen for the same time. The take is stamped with the
current wall clock, so a coach reads it (and its wrist track) exactly like a real loop take.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from coach.fixtures.generate import START_UNIX_MS, hand_samples, render_audio, timing

SAMPLERATE = 16000


def render_take(gap_ms: int) -> tuple[np.ndarray, int, int, list[dict]]:
    """Audio (float32 mono), samplerate, started_unix_ms, wrist samples in hand-log shape."""
    strums_s, stalls_s = timing(gap_ms)
    audio = render_audio(strums_s, SAMPLERATE)
    seconds = len(audio) / SAMPLERATE
    started = int(time.time() * 1000) - round(seconds * 1000)
    hands = []
    for sample in hand_samples(seconds, stalls_s):
        hand = sample["hands"][0]
        hands.append({"timestamp_ms": sample["timestamp_ms"] + started - START_UNIX_MS,
                      "handedness": hand["handedness"], "wrist": hand["wrist"],
                      "confidence": hand["confidence"]})
    return audio, SAMPLERATE, started, hands


def write_practice_take(take_dir: Path, hand_log: Path, gap_ms: int, index: int) -> Path:
    """Write the take into a local coach's --take-dir and its wrist track into --hand-log."""
    import json
    from audio.takes import write_take
    audio, sr, started, hands = render_take(gap_ms)
    hand_log.parent.mkdir(parents=True, exist_ok=True)
    with hand_log.open("a", encoding="utf-8") as stream:
        for h in hands:
            stream.write(json.dumps({"timestamp_ms": h["timestamp_ms"], "hands": [
                {"handedness": h["handedness"], "wrist": h["wrist"], "confidence": h["confidence"]}],
                "strum_hand": h["handedness"]}, separators=(",", ":")) + "\n")
    return write_take(take_dir / f"take-{started}-{index}.wav", audio, sr, started, source="loop")
