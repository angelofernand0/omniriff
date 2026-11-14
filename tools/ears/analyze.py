"""Ears (docs/COACH.md, Piece B): strum timing from a captured take.

Offline numpy/scipy, no click track. Input is a take WAV from audio/takes.py
(dry, post-gain, mono) plus its JSON sidecar. Output is a TakeReport, named
and banded like vision/eyes.py's HandReport so the coach can line the two up:
times are ms from the start of the take, and started_unix_ms is passed
through from the sidecar.

Method (deliberately simple and explainable):
  1. High-pass at 3 kHz: the pick's attack is broadband, while ringing
     strings sit lower, so soft upstrokes still stand out over loud ringing.
  2. 5 ms frames of energy -> log energy -> rise over the quietest of the
     previous 15 ms.
  3. An onset needs a rise of at least 9 dB and a level within 25 dB of the
     take's loud level (95th percentile), which rejects small bumps in
     decaying tails. It must also beat the loudest frame of the previous
     20–60 ms, so steady overtone beating in a sustained chord isn't
     mistaken for new strums. Attacks within 70 ms merge, so one strum across six
     strings counts once.
  4. Each inter-strum interval is compared with the local median interval:
     much longer = hesitation (gap), somewhat longer = late (drag),
     shorter = early (rush).

Limits, to say out loud: an intended rest in a strumming pattern looks like
a hesitation; very soft upstrokes under loud ringing can be missed; times
are accurate to roughly ±15 ms (a strum's first string can be the soft one).
Tuned on the virtual guitar's string model (tools/virtual_guitar/guitar.py);
re-check on real DI takes from the Scarlett. `highpass_hz` is adjustable for
darker pickups.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

HOP_MS = 5.0
RISE_FRAMES = 3            # compare with the previous 15 ms
MIN_GAP_MS = 70.0          # merge string-by-string attacks of one strum
HIGHPASS_HZ = 3000.0       # isolate pick attacks from string ring
RISE_DB = 9.0              # minimum rise over the previous 15 ms
RELATIVE_DB = 25.0         # onset level must be within this of the take's loud level
START_GUARD_MS = 20.0      # ignore the take's own 5 ms seam fade-in (a loop can start mid-chord)
RECENT_MAX_MS = 60.0       # onset must also exceed the loudest frame 20–60 ms earlier (rejects steady beating)
HESITATION_RATIO, LATE_RATIO, EARLY_RATIO = 1.6, 1.2, 0.8
MIN_EXTRA_MS = 120.0       # hesitation must also be this much longer than expected
MIN_STRUMS = 4             # fewer strums than this: timing can't be judged (e.g. a silent or aborted take)


@dataclass
class TakeReport:
    version: int = 1
    source: str = "tools.ears"
    take_id: str | None = None
    started_unix_ms: int | None = None
    samplerate: int = 0
    duration_s: float = 0.0
    strum_count: int = 0
    judgeable: bool = False            # False: too few strums to judge timing; never compare or credit progress
    min_strums: int = MIN_STRUMS
    onsets_ms: list = field(default_factory=list)
    intervals_ms: list = field(default_factory=list)
    median_interval_ms: float | None = None
    strum_rate_per_min: float | None = None
    tempo_stability: float = 0.0       # 1 - coefficient of variation of the even intervals, clipped to [0, 1]
    findings: list = field(default_factory=list)
    summary: str = ""

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent)


def _severity(extra_ms: float) -> str:
    # Same bands as vision/eyes.py stalls.
    return "minor" if extra_ms < 250 else "moderate" if extra_ms <= 400 else "severe"


def detect_onsets(x: np.ndarray, samplerate: int, highpass_hz: float = HIGHPASS_HZ) -> np.ndarray:
    """Return strum onset times in ms from the start of `x`."""
    x = np.asarray(x, dtype=np.float64).ravel()
    hop = max(1, int(samplerate * HOP_MS / 1000))
    if len(x) < hop * (RISE_FRAMES + 2):
        return np.zeros(0)
    sos = butter(2, min(highpass_hz, 0.45 * samplerate), btype="highpass", fs=samplerate, output="sos")
    y = sosfilt(sos, x)
    frames = len(y) // hop
    energy = np.square(y[:frames * hop]).reshape(frames, hop).mean(axis=1)
    level = 10.0 * np.log10(energy + 1e-12)
    loud = np.percentile(level, 95)
    prev = np.full(frames, np.inf)  # quietest level over the previous RISE_FRAMES frames
    for k in range(1, RISE_FRAMES + 1):
        prev[k:] = np.minimum(prev[k:], level[:-k])
    rise = np.where(np.isfinite(prev), level - prev, 0.0)
    rise = np.maximum(rise, 0.0)
    if np.max(energy) < 1e-9:  # effectively silent
        return np.zeros(0)
    recent = np.full(frames, -np.inf)  # loudest level 20..60 ms before each frame
    for k in range(RISE_FRAMES + 1, int(RECENT_MAX_MS / HOP_MS) + 1):
        recent[k:] = np.maximum(recent[k:], level[:-k])
    candidates = np.flatnonzero((rise > RISE_DB) & (level > loud - RELATIVE_DB) & (level > recent))
    onsets = []
    min_gap = MIN_GAP_MS / HOP_MS
    for idx in candidates:
        if idx * HOP_MS < START_GUARD_MS:
            continue
        if onsets and idx - onsets[-1] < min_gap:
            continue  # same strum: keep its first attack, the musically meaningful time
        onsets.append(idx)
    return np.asarray(onsets, dtype=np.float64) * HOP_MS


def analyze_timing(onsets_ms) -> tuple[list, list, float | None, float, list]:
    """Return (onsets, intervals, median interval, stability, findings) for onset times in ms."""
    onsets = [round(float(t), 1) for t in onsets_ms]
    intervals = [round(b - a, 1) for a, b in zip(onsets, onsets[1:])]
    if len(intervals) < 3:
        return onsets, intervals, (float(np.median(intervals)) if intervals else None), 0.0, []
    iv = np.asarray(intervals)
    median = float(np.median(iv))
    findings, even = [], []
    for i, value in enumerate(iv):
        lo, hi = max(0, i - 4), min(len(iv), i + 5)
        neighbours = np.delete(iv[lo:hi], i - lo)
        expected = float(np.median(neighbours)) if len(neighbours) else median
        ratio = value / expected if expected > 0 else 1.0
        at = onsets[i + 1]
        value, extra = float(value), float(value - expected)
        if ratio >= HESITATION_RATIO and extra >= MIN_EXTRA_MS:
            findings.append(dict(type="hesitation", at_ms=at, gap_ms=round(float(value), 1),
                                 expected_ms=round(expected, 1), extra_ms=round(extra, 1),
                                 severity=_severity(extra),
                                 message=f"{extra:.0f} ms pause before the strum at {at / 1000:.2f} s "
                                         "(a chord change? or an intended rest)"))
        else:
            even.append(value)
            if ratio >= LATE_RATIO:
                findings.append(dict(type="late", at_ms=at, gap_ms=round(float(value), 1),
                                     expected_ms=round(expected, 1), extra_ms=round(extra, 1),
                                     severity=_severity(extra), message=f"strum at {at / 1000:.2f} s dragged"))
            elif ratio <= EARLY_RATIO:
                findings.append(dict(type="early", at_ms=at, gap_ms=round(float(value), 1),
                                     expected_ms=round(expected, 1), extra_ms=round(extra, 1),
                                     severity=_severity(-extra), message=f"strum at {at / 1000:.2f} s rushed"))
    ev = np.asarray(even) if even else iv
    cv = float(np.std(ev) / np.mean(ev)) if np.mean(ev) > 0 else 1.0
    stability = round(min(1.0, max(0.0, 1.0 - cv)), 3)
    return onsets, intervals, median, stability, findings


def analyze_take(wav_path, sidecar_path=None) -> TakeReport:
    from audio.fileio import read_wav

    wav_path = Path(wav_path)
    data, sr = read_wav(wav_path)
    meta = {}
    side = Path(sidecar_path) if sidecar_path else wav_path.with_suffix(".json")
    if side.exists():
        meta = json.loads(side.read_text())
    onsets, intervals, median, stability, findings = analyze_timing(detect_onsets(data.mean(axis=1), sr))
    hes = [f for f in findings if f["type"] == "hesitation"]
    if len(onsets) < MIN_STRUMS:
        summary = f"Only {len(onsets)} strums detected: too few to judge timing."
    else:
        rate = 60000.0 / median
        summary = (f"{len(onsets)} strums, about {rate:.0f} per minute, stability {stability:.2f}. "
                   + (f"{len(hes)} hesitation(s), longest {max(f['extra_ms'] for f in hes):.0f} ms extra."
                      if hes else "No hesitations."))
    return TakeReport(
        take_id=meta.get("take_id", wav_path.stem), started_unix_ms=meta.get("started_unix_ms"),
        samplerate=sr, duration_s=round(len(data) / sr, 3), strum_count=len(onsets),
        judgeable=len(onsets) >= MIN_STRUMS,
        onsets_ms=onsets, intervals_ms=intervals,
        median_interval_ms=round(median, 1) if median else None,
        strum_rate_per_min=round(60000.0 / median, 1) if median else None,
        tempo_stability=stability, findings=findings, summary=summary,
    )
