"""Feel: swing and attack consistency per phrase (Ears, alongside the timing gaps).

Aditya's feedback on what actually helps: not just "there's a gap", but *which phrase* and
*what about it*: played straight when the riff swings, or attacks that jump around.

  phrases       the take split into (up to) four equal stretches of strums, in order;
  swing ratio   per phrase, the long/short ratio of consecutive strum pairs (1.0 = straight,
                about 1.5-2.0 = swung), aligned to the take's own long-short order;
  attack spread per phrase, the standard deviation in dB of each strum's attack loudness
                (the first 30 ms after the onset).

Findings compare a phrase with **the rest of the same take**, never with an outside ideal:
  straight_phrase  the take swings (median phrase ratio >= 1.3) but this phrase is near 1.0;
  uneven_attacks   this phrase's attack spread is >= 2 dB and >= 1.5x the other phrases'.
A take that is straight throughout is just "straight": Riff must not push swing on it.
Limits: equal-length phrases, not musical bars; down/up strokes naturally differ in loudness
(that is in every phrase, so the comparison still holds); ±15 ms onset accuracy limits ratios
on very fast strumming.
"""
from __future__ import annotations

import math

import numpy as np

ATTACK_MS = 30.0
SWUNG = 1.3            # take median phrase ratio at or above this: the take swings
STRAIGHT = 1.15        # a phrase at or below this, in a swung take, is played straight
UNEVEN_DB = 2.0
UNEVEN_FACTOR = 1.5
PHRASES = 4
MIN_PER_PHRASE = 4


def attack_levels_db(x: np.ndarray, samplerate: int, onsets_ms) -> list[float]:
    """How hard each strum was picked: the peak of the pick click (high-passed, like onset
    detection) in the first 30 ms after the onset, in dBFS. The low strings still ringing from
    the previous strum would otherwise swamp the attack."""
    from scipy.signal import butter, sosfilt
    x = np.asarray(x, dtype=np.float64).ravel()
    sos = butter(2, min(2000.0, 0.45 * samplerate), btype="highpass", fs=samplerate, output="sos")
    y = sosfilt(sos, x)
    span = max(1, int(samplerate * ATTACK_MS / 1000))
    levels = []
    for t in onsets_ms:
        i = max(0, int(samplerate * float(t) / 1000) - span // 6)
        seg = y[i:i + span]
        peak = float(np.max(np.abs(seg))) if len(seg) else 0.0
        levels.append(round(20 * math.log10(peak + 1e-9), 1))
    return levels


def _ratio(intervals: list[float], long_first: bool) -> float | None:
    pairs = [(intervals[i], intervals[i + 1]) for i in range(0, len(intervals) - 1, 2)]
    logs = [math.log(a / b) if long_first else math.log(b / a) for a, b in pairs if a > 0 and b > 0]
    return round(math.exp(float(np.median(logs))), 2) if logs else None


def analyze_feel(onsets_ms, levels_db) -> tuple[list[dict], list[dict], str]:
    """Return (phrases, findings, feel) where feel is 'swung', 'straight' or 'unknown'."""
    onsets = [float(t) for t in onsets_ms]
    if len(onsets) < 2 * MIN_PER_PHRASE:
        return [], [], "unknown"
    count = min(PHRASES, len(onsets) // MIN_PER_PHRASE)
    intervals = list(np.diff(onsets))
    # the take's own long-short order: which of each pair is the long one, over the whole take
    even = [intervals[i] for i in range(0, len(intervals) - 1, 2)]
    odd = [intervals[i + 1] for i in range(0, len(intervals) - 1, 2)]
    long_first = float(np.median(even)) >= float(np.median(odd))
    bounds = np.linspace(0, len(onsets), count + 1).round().astype(int)
    phrases = []
    for n in range(count):
        a, b = int(bounds[n]), int(bounds[n + 1])
        # start each phrase on the same side of a pair as the take, so ratios are comparable
        if a % 2:
            a += 1
        seg = onsets[a:b]
        ivals = list(np.diff(seg))
        lv = [levels_db[i] for i in range(a, b)] if levels_db else []
        phrases.append({
            "n": n + 1, "start_ms": round(onsets[int(bounds[n])], 1), "end_ms": round(onsets[min(b, len(onsets)) - 1], 1),
            "strums": b - int(bounds[n]),
            "swing_ratio": _ratio(ivals, long_first) if len(ivals) >= 2 else None,
            # down- and up-strokes are naturally different loudnesses: spread within each, averaged
            "attack_spread_db": (round(float(np.mean([np.std(lv[0::2]), np.std(lv[1::2])])), 1)
                                 if len(lv) >= 4 else None),
        })
    ratios = [p["swing_ratio"] for p in phrases if p["swing_ratio"]]
    take_ratio = float(np.median(ratios)) if ratios else 1.0
    feel = "swung" if take_ratio >= SWUNG else "straight"
    findings = []
    for p in phrases:
        others = [q for q in phrases if q is not p]
        if feel == "swung" and p["swing_ratio"] and p["swing_ratio"] <= STRAIGHT:
            other_ratio = float(np.median([q["swing_ratio"] for q in others if q["swing_ratio"]]))
            findings.append({"type": "straight_phrase", "phrase": p["n"], "at_ms": p["start_ms"], "end_ms": p["end_ms"],
                             "swing_ratio": p["swing_ratio"], "rest_swing_ratio": round(other_ratio, 2),
                             "message": (f"Phrase {p['n']} is played straight ({p['swing_ratio']:.1f} to 1) while the rest "
                                         f"of the take swings ({other_ratio:.1f} to 1).")})
        spreads = [q["attack_spread_db"] for q in others if q["attack_spread_db"] is not None]
        if p["attack_spread_db"] is not None and spreads:
            rest = float(np.median(spreads))
            if p["attack_spread_db"] >= UNEVEN_DB and p["attack_spread_db"] >= UNEVEN_FACTOR * max(rest, 0.5):
                findings.append({"type": "uneven_attacks", "phrase": p["n"], "at_ms": p["start_ms"], "end_ms": p["end_ms"],
                                 "spread_db": p["attack_spread_db"], "rest_spread_db": round(rest, 1),
                                 "message": (f"Your attacks in phrase {p['n']} vary by {p['attack_spread_db']:.0f} dB, "
                                             f"against about {rest:.0f} dB in the rest of the take.")})
    return phrases, findings, feel
