"""Two-hand camera tracks (all 21 points) for the PLAY-THIS riff, with planted technique faults.

Ground truth for vision/technique.py and for driving the real coach without a guitar. The
fretting hand moves each fingertip between schematic Em / Cmaj7 / G / Dsus2 shapes; the picking
hand swings down/up through every strum. A strum after a change waits for the last finger to land,
so a late finger shows up in the audio exactly as it would for a player. This is synthetic: it
proves the measurement, not that a webcam sees a real hand this cleanly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from coach.fixtures.generate import render_audio

SAMPLERATE = 16000
FPS = 30
BEAT_S = 0.5
FIRST_STRUM_S = 0.35
STRUMS = 16
CHANGES = (4, 8, 12)                 # strum index that starts each new chord
WRIST = np.array([0.25, 0.62])
MCP = {"index": (0.215, 0.53), "middle": (0.245, 0.52), "ring": (0.272, 0.53), "pinky": (0.295, 0.545)}
JOINTS = {"index": (5, 6, 7, 8), "middle": (9, 10, 11, 12), "ring": (13, 14, 15, 16), "pinky": (17, 18, 19, 20)}
# finger -> (string 0=low E .. 5=high e, fret); missing fingers hover
SHAPES = [
    {"middle": (1, 2), "ring": (2, 2)},                          # Em
    {"ring": (1, 3), "middle": (2, 2)},                          # Cmaj7
    {"middle": (0, 3), "index": (1, 2), "ring": (5, 3)},         # G
    {"index": (3, 2), "ring": (4, 3)},                           # Dsus2
]


@dataclass
class Faults:
    """What the player does wrong at every change (seconds)."""
    late_finger: str | None = None   # this finger arrives late...
    lag_s: float = 0.0               # ...by this much
    start_delay_s: float = 0.0       # fretting hand starts moving this long after it should
    wander: float = 0.0              # extra arc off the direct path, in hand-widths


def _tip(finger: str, shape: dict) -> np.ndarray:
    if finger in shape:
        string, fret = shape[finger]
        return np.array([0.30 - 0.032 * fret + 0.004 * list(MCP).index(finger), 0.37 + 0.016 * string])
    x, y = MCP[finger]
    return np.array([x, y - 0.05])           # hovering, curled above its knuckle


def _ease(u: np.ndarray | float):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


def plan(faults: Faults) -> tuple[list[float], list[dict]]:
    """Strum times and per-change finger timing (start, land) with the faults applied."""
    strums: list[float] = []
    moves: list[dict] = []
    delay = 0.0
    for i in range(STRUMS):
        t = FIRST_STRUM_S + i * BEAT_S + delay
        if i in CHANGES:
            prev = strums[-1]
            k = CHANGES.index(i)
            frm, to = SHAPES[k % 4], SHAPES[(k + 1) % 4]
            timing = {}
            for n, finger in enumerate(MCP):
                if np.linalg.norm(_tip(finger, frm) - _tip(finger, to)) < 1e-6:
                    continue
                start = prev + 0.12 + faults.start_delay_s + 0.02 * n
                land = start + 0.2 + (faults.lag_s if finger == faults.late_finger else 0.0)
                timing[finger] = (start, land)
            ready = max(land for _, land in timing.values()) + 0.03
            if ready > t:
                delay += ready - t
                t = ready
            moves.append({"from": k % 4, "to": (k + 1) % 4, "timing": timing})
        strums.append(t)
    return strums, moves


def fret_points(t: float, moves: list[dict], faults: Faults, rng) -> np.ndarray:
    pts = np.zeros((21, 2))
    pts[0] = WRIST
    for j, offset in zip((1, 2, 3, 4), ((0.02, -0.03), (0.035, -0.05), (0.045, -0.07), (0.05, -0.085))):
        pts[j] = WRIST + offset
    shape = SHAPES[0]
    current = {f: _tip(f, shape) for f in MCP}
    for move in moves:
        frm, to = SHAPES[move["from"]], SHAPES[move["to"]]
        for finger in MCP:
            a, b = _tip(finger, frm), _tip(finger, to)
            if finger not in move["timing"]:
                if t >= min(s for s, _ in move["timing"].values()):
                    current[finger] = b
                continue
            start, land = move["timing"][finger]
            if t <= start:
                continue
            u = _ease((t - start) / (land - start))
            d = b - a
            normal = np.array([-d[1], d[0]]) / (np.linalg.norm(d) or 1.0)
            arc = (0.012 + faults.wander * 0.1) * np.sin(np.pi * u)
            current[finger] = a + d * u + normal * arc
    for finger, (mcp, pip, dip, tip) in JOINTS.items():
        m = np.array(MCP[finger])
        pts[mcp] = m
        pts[pip] = m + 0.4 * (current[finger] - m) + [0, -0.008]
        pts[dip] = m + 0.7 * (current[finger] - m) + [0, -0.006]
        pts[tip] = current[finger]
    return pts + rng.normal(0, 0.0015, pts.shape)


def pick_points(t: float, strums: list[float], rng) -> np.ndarray:
    """Wrist at the top before a downstroke, at the bottom on it; it waits when the strum waits."""
    phase = np.interp(t, strums, np.arange(len(strums)), left=-0.5, right=len(strums) - 0.5)
    wrist = np.array([0.72, 0.56 + 0.05 * np.cos(np.pi * (phase + 1))])
    pts = np.zeros((21, 2))
    template = np.array([[0, 0], [-.02, -.02], [-.03, -.04], [-.035, -.06], [-.035, -.075],
                         [0, -.07], [.0, -.095], [.0, -.11], [.0, -.12], [.02, -.07], [.02, -.095], [.02, -.105],
                         [.02, -.11], [.04, -.065], [.04, -.085], [.04, -.095], [.04, -.1], [.055, -.055],
                         [.055, -.07], [.055, -.08], [.055, -.085]])
    pts[:] = wrist + template
    return pts + rng.normal(0, 0.0015, pts.shape)


def render(faults: Faults, *, seed: int = 3) -> tuple[np.ndarray, int, int, list[dict], list[float]]:
    """Audio, samplerate, started_unix_ms, hand-log records (both hands, 21 points), strum times."""
    strums, moves = plan(faults)
    audio = render_audio(strums, SAMPLERATE)
    seconds = len(audio) / SAMPLERATE
    started = int(time.time() * 1000) - round(seconds * 1000)
    rng = np.random.default_rng(seed)
    records = []
    for frame in range(int(seconds * FPS)):
        t = frame / FPS
        f = fret_points(t, moves, faults, rng)
        p = pick_points(t, strums, rng)
        # selfie-mirrored camera: MediaPipe labels the player's right (picking) hand "Left"
        records.append({"timestamp_ms": started + round(t * 1000), "hands": [
            {"handedness": "Right", "confidence": 0.95, "wrist": [round(f[0, 0], 4), round(f[0, 1], 4)],
             "landmarks": [[round(x, 4), round(y, 4)] for x, y in f]},
            {"handedness": "Left", "confidence": 0.95, "wrist": [round(p[0, 0], 4), round(p[0, 1], 4)],
             "landmarks": [[round(x, 4), round(y, 4)] for x, y in p]}]})
    return audio, SAMPLERATE, started, records, strums
