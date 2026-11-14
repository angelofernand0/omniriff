"""Biomechanical Hand Movement & Strum Continuity Analyzer (Coach 'Eyes' - Piece C).

Detects strum cadence, estimates tempo, and identifies 'pendulum stalls'
(where the strumming hand freezes during chord changes).
Emits the standardized JSON HandReport defined in docs/COACH.md.
"""
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class StallEvent:
    start_time_s: float
    end_time_s: float
    duration_ms: int
    position: Tuple[float, float]
    severity: str  # 'minor' (<250ms), 'moderate' (250-400ms), 'severe' (>400ms)
    message: str


@dataclass
class HandReport:
    version: int = 1
    source: str = 'vision.eyes'
    duration_s: float = 0.0
    sample_count: int = 0
    strum_count: int = 0
    tempo_bpm: Optional[float] = None
    tempo_stability: float = 0.0
    motion_continuity_score: float = 0.0
    stalls: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ''

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent)


class HandMovementAnalyzer:
    """Analyzes continuous wrist movement to evaluate guitar strumming technique."""

    def __init__(
        self,
        stall_speed_threshold: float = 0.20,  # Normalized units/sec below which motion is considered stalled
        min_stall_duration_s: float = 0.18,    # Minimum duration (180ms) to register as a freeze
        min_stroke_amplitude: float = 0.05,    # Minimum vertical stroke travel to count as a strum
    ):
        if not math.isfinite(stall_speed_threshold) or stall_speed_threshold <= 0:
            raise ValueError('stall_speed_threshold must be positive and finite')
        if not math.isfinite(min_stall_duration_s) or min_stall_duration_s <= 0:
            raise ValueError('min_stall_duration_s must be positive and finite')
        if not math.isfinite(min_stroke_amplitude) or min_stroke_amplitude <= 0:
            raise ValueError('min_stroke_amplitude must be positive and finite')

        self.stall_speed_threshold = stall_speed_threshold
        self.min_stall_duration_s = min_stall_duration_s
        self.min_stroke_amplitude = min_stroke_amplitude

        # State tracking
        self.samples: List[Tuple[float, float, float]] = []  # (t, x, y)
        self.stalls: List[StallEvent] = []
        self._stall_start_t: Optional[float] = None
        self._stall_last_t: Optional[float] = None
        self._stall_start_pos: Optional[Tuple[float, float]] = None

    def reset(self):
        self.samples.clear()
        self.stalls.clear()
        self._stall_start_t = None
        self._stall_last_t = None
        self._stall_start_pos = None

    def add_sample(self, t: float, x: float, y: float):
        """Add a single wrist tracking point at monotonic time t (seconds)."""
        if not all(math.isfinite(v) for v in (t, x, y)):
            return
        if self.samples and t <= self.samples[-1][0]:
            return  # Reject out-of-order or duplicate timestamps
        self.samples.append((t, x, y))

        # Real-time stall tracking
        if len(self.samples) >= 2:
            prev_t, prev_x, prev_y = self.samples[-2]
            dt = t - prev_t
            if dt > 0:
                dist = math.hypot(x - prev_x, y - prev_y)
                speed = dist / dt

                if speed < self.stall_speed_threshold:
                    if self._stall_start_t is None:
                        self._stall_start_t = prev_t
                        self._stall_start_pos = (prev_x, prev_y)
                    self._stall_last_t = t
                else:
                    if self._stall_start_t is not None:
                        stall_end_t = self._stall_last_t or prev_t
                        duration = stall_end_t - self._stall_start_t
                        if duration >= self.min_stall_duration_s:
                            self._record_stall(self._stall_start_t, stall_end_t, self._stall_start_pos or (prev_x, prev_y))
                        self._stall_start_t = None
                        self._stall_last_t = None
                        self._stall_start_pos = None

    def _record_stall(self, start_t: float, end_t: float, pos: Tuple[float, float]):
        dur_ms = int(round((end_t - start_t) * 1000))
        if dur_ms < 250:
            severity = 'minor'
        elif dur_ms <= 400:
            severity = 'moderate'
        else:
            severity = 'severe'

        msg = f"Strumming hand froze for {dur_ms} ms at t={start_t:.2f}s"
        self.stalls.append(StallEvent(
            start_time_s=round(start_t, 3),
            end_time_s=round(end_t, 3),
            duration_ms=dur_ms,
            position=(round(pos[0], 3), round(pos[1], 3)),
            severity=severity,
            message=msg,
        ))

    def analyze(self) -> HandReport:
        """Run full post-take analysis over all accumulated samples and produce HandReport."""
        # Close any active open stall at end of take
        if self._stall_start_t is not None and self.samples:
            stall_end_t = self._stall_last_t or self.samples[-1][0]
            dur = stall_end_t - self._stall_start_t
            if dur >= self.min_stall_duration_s:
                self._record_stall(self._stall_start_t, stall_end_t, self._stall_start_pos or (self.samples[-1][1], self.samples[-1][2]))
            self._stall_start_t = None
            self._stall_last_t = None

        if len(self.samples) < 5:
            return HandReport(
                sample_count=len(self.samples),
                summary="Insufficient hand tracking data to evaluate technique (under 5 frames)."
            )

        duration_s = self.samples[-1][0] - self.samples[0][0]
        if duration_s <= 0.1:
            return HandReport(
                duration_s=round(duration_s, 3),
                sample_count=len(self.samples),
                summary="Take duration too short for rhythmic evaluation."
            )

        y_vals = [s[2] for s in self.samples]
        times = [s[0] for s in self.samples]

        # Smooth with small rolling average to avoid single-frame noise
        smoothed_y = []
        win = 2
        for i in range(len(y_vals)):
            sub = y_vals[max(0, i - win):min(len(y_vals), i + win + 1)]
            smoothed_y.append(sum(sub) / len(sub))

        # Robust hysteresis peak and valley detector
        strokes: List[Tuple[float, float, str]] = []
        last_extrema_y = smoothed_y[0]
        last_extrema_t = times[0]
        direction = 0  # +1 for downward (increasing y), -1 for upward (decreasing y)

        for i in range(1, len(smoothed_y)):
            y = smoothed_y[i]
            t = times[i]
            if direction >= 0:
                if y > last_extrema_y:
                    last_extrema_y = y
                    last_extrema_t = t
                elif last_extrema_y - y >= self.min_stroke_amplitude:
                    strokes.append((last_extrema_t, last_extrema_y, 'down_reversal'))
                    direction = -1
                    last_extrema_y = y
                    last_extrema_t = t
            if direction <= 0:
                if y < last_extrema_y:
                    last_extrema_y = y
                    last_extrema_t = t
                elif y - last_extrema_y >= self.min_stroke_amplitude:
                    strokes.append((last_extrema_t, last_extrema_y, 'up_reversal'))
                    direction = 1
                    last_extrema_y = y
                    last_extrema_t = t

        strum_count = len(strokes)
        tempo_bpm = None
        tempo_stability = 0.0

        if len(strokes) >= 3:
            intervals = [strokes[i][0] - strokes[i - 1][0] for i in range(1, len(strokes))]
            valid_intervals = [dt for dt in intervals if 0.08 <= dt <= 2.0]
            if len(valid_intervals) >= 2:
                mean_dt = sum(valid_intervals) / len(valid_intervals)
                if mean_dt > 0:
                    # Quarter-note BPM: each full pendulum cycle (down + up stroke) is 1 beat
                    tempo_bpm = round(60.0 / (mean_dt * 2.0), 1)

                variance = sum((dt - mean_dt) ** 2 for dt in valid_intervals) / len(valid_intervals)
                std_dt = math.sqrt(variance)
                cv = std_dt / max(mean_dt, 1e-4)
                tempo_stability = round(max(0.0, min(1.0, 1.0 - cv * 2.0)), 2)

        # Motion continuity score: fraction of time spent in active rhythmic motion
        total_stall_s = sum(s.duration_ms / 1000.0 for s in self.stalls)
        continuity = max(0.0, min(1.0, 1.0 - (total_stall_s / max(duration_s, 0.1))))
        continuity_score = round(continuity, 2)

        # Generate actionable teacher summary
        if not self.stalls:
            if strum_count >= 4 and tempo_bpm:
                summary = (
                    f"Excellent pendulum rhythm! Hand maintained continuous motion at ~{tempo_bpm:.0f} BPM "
                    f"with {tempo_stability * 100:.0f}% cadence stability. Zero stalls detected."
                )
            else:
                summary = "Smooth motion throughout take. Zero stalls detected."
        else:
            longest = max(self.stalls, key=lambda s: s.duration_ms)
            summary = (
                f"Strumming hand froze {len(self.stalls)} time{'s' if len(self.stalls) > 1 else ''} "
                f"(longest: {longest.duration_ms} ms at {longest.start_time_s}s). "
                f"Cause: hand stops swinging during chord changes. "
                f"Drill: Keep the pendulum arm swinging steadily even if fretting hand is late."
            )

        return HandReport(
            version=1,
            source='vision.eyes',
            duration_s=round(duration_s, 3),
            sample_count=len(self.samples),
            strum_count=strum_count,
            tempo_bpm=tempo_bpm,
            tempo_stability=tempo_stability,
            motion_continuity_score=continuity_score,
            stalls=[asdict(s) for s in self.stalls],
            summary=summary,
        )


def generate_synthetic_strum_take(
    duration_s: float = 6.0,
    fps: float = 30.0,
    tempo_bpm: float = 120.0,
    stall_start_s: Optional[float] = 3.0,
    stall_duration_s: float = 0.40,
) -> List[Tuple[float, float, float]]:
    """Synthesize a realistic wrist trajectory with continuous pendulum motion and an optional stall."""
    samples = []
    stroke_hz = tempo_bpm / 60.0  # 120 strums/min = 2.0 strokes/sec
    total_frames = int(duration_s * fps)
    dt = 1.0 / fps

    for i in range(total_frames):
        t = i * dt
        # Normal pendulum motion: y oscillates around center 0.65 with amplitude 0.15
        if stall_start_s is not None and stall_start_s <= t < (stall_start_s + stall_duration_s):
            # Hand freezes at top of upstroke
            y = 0.50
            x = 0.40
        else:
            phase = 2.0 * math.pi * stroke_hz * t
            y = 0.65 + 0.15 * math.cos(phase)
            x = 0.40 + 0.03 * math.sin(phase)

        samples.append((round(t, 4), round(x, 4), round(y, 4)))
    return samples


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--demo', action='store_true', help='run synthetic demonstration with known ground-truth stall')
    p.add_argument('--output', type=Path, help='output path for JSON HandReport')
    p.add_argument('--landmarks', type=Path, help='JSONL file containing timestamp and hand landmarks')
    args = p.parse_args(argv)

    if args.demo:
        print("=== Coach Eyes: Biomechanical Technique Analysis Demo ===")
        print("Synthesizing 6-second guitar take at 120 BPM with 400ms stall at t=3.0s...")
        samples = generate_synthetic_strum_take(
            duration_s=6.0, fps=30.0, tempo_bpm=120.0, stall_start_s=3.0, stall_duration_s=0.40
        )
        analyzer = HandMovementAnalyzer()
        for t, x, y in samples:
            analyzer.add_sample(t, x, y)
        report = analyzer.analyze()

        print(f"\nDuration:          {report.duration_s}s ({report.sample_count} frames)")
        print(f"Strum Count:       {report.strum_count} strokes")
        print(f"Detected Tempo:    {report.tempo_bpm} BPM")
        print(f"Continuity Score:  {int(report.motion_continuity_score * 100)}%")
        print(f"Stalls Detected:   {len(report.stalls)}")
        for s in report.stalls:
            print(f"  * {s['message']} [{s['severity'].upper()}]")
        print(f"\nVerdict: {report.summary}\n")

        if args.output:
            args.output.write_text(report.to_json() + '\n')
            print(f"Saved HandReport to {args.output}")
        return

    if args.landmarks:
        analyzer = HandMovementAnalyzer()
        with args.landmarks.open('r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                t = data.get('timestamp_ms', 0) / 1000.0
                pts = data.get('landmarks', [])
                if pts:
                    analyzer.add_sample(t, pts[0][0], pts[0][1])
        report = analyzer.analyze()
        if args.output:
            args.output.write_text(report.to_json() + '\n')
            print(f"Saved HandReport to {args.output}")
        else:
            print(report.to_json())
        return

    p.print_help()


if __name__ == '__main__':
    main()
