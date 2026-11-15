"""TechniqueReport: what the hands did at each chord change, measured from the camera.

Eyes (vision/eyes.py) answers "did the strumming wrist stop?". This answers *why* a change
was late, from all 21 points of both hands (vision hand log / the website's camera) and Ears'
strum times:

  fretting hand  when the fingers start moving relative to the last strum, how long the change
                 takes, which finger lands last and by how much, whether the chord was ready
                 when the next strum was due, how far the whole hand jumped along the neck,
                 and how far the fingertips wander off the straight path between shapes;
  picking hand   whether it stopped during the change, and its stroke size.

Everything is measured in 2-D image coordinates normalised by the hand's own size
(wrist -> middle-finger knuckle = 1 "hand"), so camera distance doesn't matter. What a 2-D
webcam cannot see is said plainly: finger *height* off the fretboard, pressure, pick angle,
which fret/string. Findings carry numbers and a plain message; the coach must not go beyond them.

    python -m vision.technique runs/hand.jsonl --take runs/takes/take-123.wav
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

FINGERS = {"index": 8, "middle": 12, "ring": 16, "pinky": 20}
WINDOW_S = 0.05          # half-window for displacement-based motion (robust to landmark jitter)
MOVE_HANDS = 0.06        # a (smoothed) fingertip moving > 0.06 hand-sizes per 100 ms is moving
MIN_TRAVEL_HANDS = 0.12  # a finger that ends > 0.12 hand-sizes from where it started took part in the change
LATE_FINGER_MS = 100     # a finger landing this much after the others is called out
WANDER_HANDS = 0.35      # fingertip path bulging this far off the straight line between shapes
PICK_STOP_S = 0.2        # picking wrist still for this long during a change = it stopped


@dataclass
class TechniqueReport:
    version: int = 1
    source: str = "vision.technique"
    take_id: str = ""
    available: bool = False
    reason: str = ""
    frames: int = 0
    both_hands_frames: int = 0
    hand_size: float | None = None
    picking: dict = field(default_factory=dict)
    changes: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    summary: str = ""
    limits: str = ("2-D webcam: measures timing and in-plane movement of each fingertip and both "
                   "wrists; cannot see finger height off the fretboard, pressure, pick angle, or "
                   "which string or fret.")

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def _load(log_path: Path, start_ms: float, end_ms: float) -> list[dict]:
    records = []
    with Path(log_path).open(encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = record.get("timestamp_ms")
            if isinstance(ts, (int, float)) and start_ms - 300 <= ts <= end_ms + 300:
                records.append(record)
    records.sort(key=lambda r: r["timestamp_ms"])
    return records


def _tracks(records: list[dict]) -> tuple[dict[str, tuple[np.ndarray, np.ndarray]], int]:
    """Per handedness label: (times_s, points[frames, 21, 2]) from frames that carry all 21 points."""
    by_label: dict[str, list] = {"Left": [], "Right": []}
    both = 0
    t0 = records[0]["timestamp_ms"] if records else 0
    for record in records:
        hands = [h for h in record.get("hands", []) if isinstance(h.get("landmarks"), list) and len(h["landmarks"]) == 21]
        labels = {h.get("handedness") for h in hands}
        if len(hands) == 2 and labels == {"Left", "Right"}:
            both += 1
        for hand in hands:
            label = hand.get("handedness")
            if label in by_label:
                by_label[label].append(((record["timestamp_ms"] - t0) / 1000.0, hand["landmarks"]))
    out = {}
    for label, rows in by_label.items():
        if len(rows) >= 10:
            times = np.array([r[0] for r in rows], dtype=float)
            pts = np.array([r[1] for r in rows], dtype=float)
            out[label] = (times, pts)
    return out, both


def _windowed_disp(times: np.ndarray, xy: np.ndarray) -> np.ndarray:
    """Displacement over +-WINDOW_S around each frame (per frame, in the input's units)."""
    idx_lo = np.searchsorted(times, times - WINDOW_S, side="left")
    idx_hi = np.clip(np.searchsorted(times, times + WINDOW_S, side="right") - 1, 0, len(times) - 1)
    return np.linalg.norm(xy[idx_hi] - xy[idx_lo], axis=-1)


def _smooth(xy: np.ndarray, k: int = 5) -> np.ndarray:
    """Moving average over k frames per coordinate (landmark jitter is ~0.002 of the image)."""
    if len(xy) < k:
        return xy
    kernel = np.ones(k) / k
    pad = np.pad(xy, ((k // 2, k // 2), (0, 0)), mode="edge")
    return np.stack([np.convolve(pad[:, c], kernel, mode="valid") for c in range(xy.shape[1])], axis=1)


def _segments(mask: np.ndarray, times: np.ndarray, merge_s: float) -> list[tuple[int, int]]:
    segs = []
    i = 0
    n = len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            if segs and times[i] - times[segs[-1][1]] <= merge_s:
                segs[-1] = (segs[-1][0], j)
            else:
                segs.append((i, j))
            i = j + 1
        else:
            i += 1
    return segs


def _at(times: np.ndarray, t: float) -> int:
    return int(np.clip(np.searchsorted(times, t), 0, len(times) - 1))


def _ms(value: float) -> int:
    return int(round(value * 1000))


def _seconds_words(t_s: float) -> str:
    return f"{t_s:.1f} s"


def analyze(records: list[dict], take: dict | None = None, take_id: str = "") -> TechniqueReport:
    """records: hand-log lines inside the take window; take: Ears TakeReport dict (onsets, median)."""
    report = TechniqueReport(take_id=take_id, frames=len(records))
    if not records:
        report.reason = "no camera frames during this take"
        report.summary = "No camera data for this take."
        return report
    tracks, report.both_hands_frames = _tracks(records)
    if not tracks:
        report.reason = "camera frames have only the wrist point (old hand log); no finger data"
        report.summary = "Only wrist positions were recorded, so fingers can't be analysed."
        return report
    t_origin = (records[0]["timestamp_ms"] - (take or {}).get("started_unix_ms", records[0]["timestamp_ms"])) / 1000.0

    # Which hand picks: the one whose wrist swings most up and down. Labels can be mirrored.
    swing = {label: float(np.std(pts[:, 0, 1])) for label, (times, pts) in tracks.items()}
    pick_label = max(swing, key=swing.get)
    fret_label = next((label for label in tracks if label != pick_label), None)
    sizes = [float(np.median(np.linalg.norm(pts[:, 9] - pts[:, 0], axis=-1))) for _, pts in tracks.values()]
    hand = max(1e-4, float(np.median(sizes)))
    report.hand_size = round(hand, 4)

    onsets = [o / 1000.0 for o in (take or {}).get("onsets_ms") or []]
    beat = ((take or {}).get("median_interval_ms") or 0) / 1000.0
    if not beat and len(onsets) > 2:
        beat = float(np.median(np.diff(onsets)))

    # ---- picking hand ----
    p_times, p_pts = tracks[pick_label]
    p_times = p_times + t_origin
    wrist_y = p_pts[:, 0, 1]
    p_disp = _windowed_disp(p_times, p_pts[:, 0]) / hand
    still = p_disp < 0.06
    stops = [(p_times[a], p_times[b]) for a, b in _segments(still, p_times, 0.04)
             if p_times[b] - p_times[a] >= PICK_STOP_S]
    strokes = []
    ys = wrist_y
    for i in range(1, len(ys) - 1):
        if (ys[i] - ys[i - 1]) * (ys[i + 1] - ys[i]) < 0:
            strokes.append(ys[i])
    amps = np.abs(np.diff(strokes)) / hand if len(strokes) > 2 else np.array([])
    amps = amps[amps > 0.1] if len(amps) else amps
    report.picking = {
        "hand": pick_label,
        "stroke_size_hands": round(float(np.median(amps)), 2) if len(amps) else None,
        "stops": [{"start_s": round(a, 2), "end_s": round(b, 2), "ms": _ms(b - a)} for a, b in stops],
    }

    if fret_label is None:
        report.reason = "only one hand in view: frame the camera so it sees the fretting hand on the neck too"
        report.available = True
        report.summary = "Only the picking hand was in view; no finger analysis."
        return report

    # ---- fretting hand: find chord changes from fingertip motion ----
    f_times, f_pts = tracks[fret_label]
    f_times = f_times + t_origin
    tips = {name: _smooth(f_pts[:, i]) for name, i in FINGERS.items()}
    disp = {name: _windowed_disp(f_times, xy) / hand for name, xy in tips.items()}
    moving_any = np.max(np.stack(list(disp.values())), axis=0) > MOVE_HANDS
    for a, b in _segments(moving_any, f_times, 0.15):
        ta, tb = f_times[a], f_times[b]
        if not 0.05 <= tb - ta <= 1.6:
            continue
        before, after = _at(f_times, ta - 0.15), _at(f_times, tb + 0.15)
        fingers = {}
        for name, xy in tips.items():
            p0, p1 = xy[before], xy[after]
            travel = float(np.linalg.norm(p1 - p0)) / hand
            if travel < MIN_TRAVEL_HANDS:
                continue
            seg = xy[before:after + 1]
            ts = f_times[before:after + 1]
            near = max(0.06, 0.12 * travel) * hand          # "at the old / new spot" tolerance
            left = np.nonzero(np.linalg.norm(seg - p0, axis=-1) > near)[0]
            away = np.nonzero(np.linalg.norm(seg - p1, axis=-1) > near)[0]
            if not len(left) or not len(away):
                continue
            start = float(ts[left[0]])
            land = float(ts[min(away[-1] + 1, len(ts) - 1)])
            # wander: how far the tip strays from the straight line between its two shapes
            d = p1 - p0
            length = float(np.linalg.norm(d)) or 1e-9
            rel = seg - p0
            off = np.abs(rel[:, 0] * d[1] - rel[:, 1] * d[0]) / length
            fingers[name] = {"start_s": round(start, 3), "land_s": round(land, 3),
                             "travel_hands": round(travel, 2), "wander_hands": round(float(np.max(off)) / hand, 2)}
        if not fingers:
            continue
        start = min(f["start_s"] for f in fingers.values())
        land = max(f["land_s"] for f in fingers.values())
        last = max(fingers, key=lambda n: fingers[n]["land_s"])
        others = [f["land_s"] for n, f in fingers.items() if n != last]
        lag = (fingers[last]["land_s"] - float(np.median(others))) if others else 0.0
        wrist_jump = float(np.linalg.norm(f_pts[after, 0] - f_pts[before, 0])) / hand
        change = {"n": len(report.changes) + 1, "start_s": round(start, 2), "landed_s": round(land, 2),
                  "duration_ms": _ms(land - start), "fingers": fingers, "last_finger": last,
                  "last_finger_lag_ms": _ms(lag), "hand_shift_hands": round(wrist_jump, 2)}
        prev = [o for o in onsets if o <= start + 0.02]
        nxt = [o for o in onsets if o > start + 0.02]
        if prev and beat:
            due = prev[-1] + beat
            change["after_last_strum_ms"] = _ms(start - prev[-1])
            change["ready_vs_beat_ms"] = _ms(land - due)          # > 0: chord not ready when the strum was due
            if nxt:
                change["next_strum_late_ms"] = _ms(nxt[0] - due)
        overlap = [s for s in stops if s[0] < land + 0.1 and s[1] > start - 0.1]
        change["picking_stopped_ms"] = _ms(max((s[1] - s[0] for s in overlap), default=0.0))
        report.changes.append(change)

    report.available = True
    report.findings = _findings(report.changes, report.picking, beat)
    report.summary = (report.findings[0]["message"] if report.findings
                      else f"{len(report.changes)} chord change(s) seen; fingers arrived together and on time.")
    if not report.changes:
        report.summary = "No chord changes seen in the fretting hand."
    return report


def _findings(changes: list[dict], picking: dict, beat: float) -> list[dict]:
    """Rank the specific, measured causes. One message each, numbers included."""
    out = []
    for c in changes:
        late = c.get("next_strum_late_ms", 0)
        where = f"the change at {_seconds_words(c['start_s'])}"
        if c["last_finger_lag_ms"] >= LATE_FINGER_MS:
            out.append({"type": "late_finger", "change": c["n"], "finger": c["last_finger"],
                        "lag_ms": c["last_finger_lag_ms"], "strum_late_ms": late, "at_s": c["landed_s"],
                        "message": (f"In {where} your {c['last_finger']} finger lands {c['last_finger_lag_ms']} ms after "
                                    f"the other fingers" + (f", and the next strum came {late} ms late." if late > 40 else "."))})
        if beat and c.get("after_last_strum_ms") is not None and c.get("ready_vs_beat_ms", 0) > 40 \
                and c["after_last_strum_ms"] > 0.6 * beat * 1000 and c["last_finger_lag_ms"] < LATE_FINGER_MS:
            out.append({"type": "late_start", "change": c["n"], "after_last_strum_ms": c["after_last_strum_ms"],
                        "ready_vs_beat_ms": c["ready_vs_beat_ms"], "at_s": c["start_s"],
                        "message": (f"In {where} your fretting hand only starts moving {c['after_last_strum_ms']} ms after "
                                    f"the last strum, so the chord is {c['ready_vs_beat_ms']} ms late for the beat.")})
        if c.get("ready_vs_beat_ms", 0) > 40 and c["duration_ms"] > 0.8 * beat * 1000 and c["last_finger_lag_ms"] < LATE_FINGER_MS:
            out.append({"type": "slow_change", "change": c["n"], "duration_ms": c["duration_ms"], "at_s": c["start_s"],
                        "message": f"In {where} the fingers take {c['duration_ms']} ms to reach the new shape, longer than one strum."})
        wander = max(c["fingers"].values(), key=lambda f: f["wander_hands"])
        name = max(c["fingers"], key=lambda n: c["fingers"][n]["wander_hands"])
        if wander["wander_hands"] >= WANDER_HANDS:
            out.append({"type": "finger_wander", "change": c["n"], "finger": name, "wander_hands": wander["wander_hands"],
                        "at_s": c["start_s"],
                        "message": (f"In {where} your {name} finger swings {wander['wander_hands']:.1f} hand-widths off the "
                                    "direct path between the two shapes.")})
        if c["picking_stopped_ms"] >= PICK_STOP_S * 1000:
            out.append({"type": "picking_stop", "change": c["n"], "ms": c["picking_stopped_ms"], "at_s": c["start_s"],
                        "message": f"Your picking hand stops for {c['picking_stopped_ms']} ms during {where}."})
    rank = {"late_finger": 0, "late_start": 1, "slow_change": 2, "picking_stop": 3, "finger_wander": 4}
    severity = lambda f: f.get("lag_ms") or f.get("ready_vs_beat_ms") or f.get("duration_ms") or f.get("ms") or 0
    out.sort(key=lambda f: (rank[f["type"]], -severity(f)))
    # Repeated causes (same finger every change) are the strongest signal: say so once, at the top.
    late = [f for f in out if f["type"] == "late_finger"]
    if len(late) >= 2 and len({f["finger"] for f in late}) == 1:
        worst = max(late, key=lambda f: f["lag_ms"])
        out.insert(0, {"type": "pattern", "finger": worst["finger"], "count": len(late), "lag_ms": worst["lag_ms"],
                       "message": (f"Your {worst['finger']} finger is the last to land in {len(late)} of "
                                   f"{len(changes)} changes (up to {worst['lag_ms']} ms behind the others).")})
    return out[:8]


def report_for_take(log_path: Path, sidecar: dict, take: dict | None) -> dict:
    records = _load(log_path, sidecar["started_unix_ms"], sidecar["ended_unix_ms"])
    return asdict(analyze(records, take, sidecar.get("take_id", "")))


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("hand_log", type=Path)
    parser.add_argument("--take", type=Path, required=True, help="take WAV (its .json sidecar is read; Ears runs on it)")
    args = parser.parse_args(argv)
    from tools.ears.analyze import analyze_take
    sidecar = json.loads(args.take.with_suffix(".json").read_text())
    ear = json.loads(analyze_take(args.take, args.take.with_suffix(".json")).to_json())
    print(json.dumps(report_for_take(args.hand_log, sidecar, ear), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
