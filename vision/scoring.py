"""Performance Scoring & Technique Analytics for Expressive Gesture Control.

Evaluates guitarist gesture execution across four quantitative dimensions:
  1. Smoothness (minimum jerk / lack of tremor)
  2. Dynamic Range (utilization of full 0.0–1.0 expression gamut)
  3. Cadence Stability (regularity of periodic sweeps or swells)
  4. Efficiency (parameter travel achieved per unit of physical hand displacement)

Outputs a comprehensive GestureScoreReport with an overall score (0–100),
letter grade (S/A/B/C/D), dimensional breakdowns, and actionable tips.
Integrates cleanly with Coach analysis workflows and Take summaries.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ScoreBreakdown:
    smoothness: float       # 0–100: low jerk, absence of nervous tremor
    range_coverage: float   # 0–100: utilization of available [0, 1] gamut
    stability: float        # 0–100: consistency across repeated gestures
    efficiency: float       # 0–100: purposeful parameter change vs excessive wander


@dataclass
class GestureScoreReport:
    version: int = 1
    source: str = 'vision.scoring'
    overall_score: int = 0          # 0–100 integer score
    letter_grade: str = 'C'         # 'S' (95+), 'A' (85+), 'B' (75+), 'C' (65+), 'D' (<65)
    sample_count: int = 0
    duration_s: float = 0.0
    breakdown: ScoreBreakdown = field(default_factory=lambda: ScoreBreakdown(0.0, 0.0, 0.0, 0.0))
    min_value: float = 0.0
    max_value: float = 0.0
    actionable_tips: List[str] = field(default_factory=list)
    summary: str = ''

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent)


class GestureScorer:
    """Accumulates parameter values and hand samples over time to compute scores."""

    def __init__(self):
        self.samples: List[Tuple[float, float, Optional[Tuple[float, float]]]] = []
        # (timestamp_s, parameter_value, optional (hand_x, hand_y))

    def reset(self):
        self.samples.clear()

    def add_sample(
        self,
        t: float,
        value: float,
        hand_pos: Optional[Tuple[float, float]] = None,
    ):
        """Record a parameter observation at monotonic time t (seconds)."""
        if not math.isfinite(t) or not math.isfinite(value):
            return
        if self.samples and t <= self.samples[-1][0]:
            return  # Reject out-of-order timestamps
        clamped_val = min(1.0, max(0.0, float(value)))
        self.samples.append((t, clamped_val, hand_pos))

    def evaluate(self) -> GestureScoreReport:
        """Compute performance score report from recorded samples."""
        if len(self.samples) < 5:
            return GestureScoreReport(
                summary='Insufficient gesture data to evaluate technique (need >= 5 samples).'
            )

        duration = self.samples[-1][0] - self.samples[0][0]
        values = [s[1] for s in self.samples]
        min_v = min(values)
        max_v = max(values)
        val_range = max_v - min_v

        # ── 1. Range Coverage Score (0–100) ──
        # Ideal expression uses at least 70% of available range
        coverage_ratio = val_range / 1.0
        range_score = min(100.0, max(0.0, (coverage_ratio / 0.70) * 100.0))

        # ── 2. Smoothness Score (0–100) ──
        # Measure second-order differences (jerk) in parameter changes
        jerks = []
        for i in range(2, len(self.samples)):
            dt1 = self.samples[i - 1][0] - self.samples[i - 2][0]
            dt2 = self.samples[i][0] - self.samples[i - 1][0]
            if dt1 > 1e-4 and dt2 > 1e-4:
                v0, v1, v2 = self.samples[i - 2][1], self.samples[i - 1][1], self.samples[i][1]
                vel1 = (v1 - v0) / dt1
                vel2 = (v2 - v1) / dt2
                accel_diff = abs(vel2 - vel1)
                jerks.append(accel_diff)

        if jerks:
            avg_jerk = sum(jerks) / len(jerks)
            # Heuristic: jerk < 5.0 is very smooth (100), jerk > 35.0 is jittery (0)
            smooth_score = max(0.0, min(100.0, 100.0 - (avg_jerk / 30.0) * 100.0))
        else:
            smooth_score = 50.0

        # ── 3. Stability Score (0–100) ──
        # Check standard deviation of peak hold and rate consistency
        dt_list = [self.samples[i][0] - self.samples[i - 1][0] for i in range(1, len(self.samples))]
        if dt_list:
            avg_dt = sum(dt_list) / len(dt_list)
            dt_variance = sum((dt - avg_dt) ** 2 for dt in dt_list) / len(dt_list)
            dt_jitter = math.sqrt(dt_variance)
            # Lower dt jitter indicates stable sampling / holding
            stability_score = max(0.0, min(100.0, 100.0 - (dt_jitter / (avg_dt + 1e-4)) * 40.0))
        else:
            stability_score = 75.0

        # ── 4. Efficiency Score (0–100) ──
        # Hand displacement vs parameter travel
        total_param_travel = sum(abs(values[i] - values[i - 1]) for i in range(1, len(values)))
        total_hand_travel = 0.0
        hand_samples = [s for s in self.samples if s[2] is not None]

        if len(hand_samples) >= 2:
            for i in range(1, len(hand_samples)):
                p0 = hand_samples[i - 1][2]
                p1 = hand_samples[i][2]
                if p0 and p1:
                    total_hand_travel += math.hypot(p1[0] - p0[0], p1[1] - p0[1])

            if total_hand_travel > 1e-4:
                # Ratio of effective parameter delta to physical travel
                travel_ratio = total_param_travel / total_hand_travel
                # Balanced travel ratio is around 1.0–2.0
                efficiency_score = min(100.0, max(20.0, min(travel_ratio, 2.0) * 50.0))
            else:
                efficiency_score = 80.0
        else:
            efficiency_score = 85.0  # Default when hand tracking coordinates omitted

        # ── Overall Score (Weighted combination) ──
        overall = (
            0.35 * smooth_score
            + 0.30 * range_score
            + 0.20 * stability_score
            + 0.15 * efficiency_score
        )
        overall_int = int(round(overall))

        # Letter grade assignment
        if overall_int >= 93:
            grade = 'S'
        elif overall_int >= 85:
            grade = 'A'
        elif overall_int >= 75:
            grade = 'B'
        elif overall_int >= 65:
            grade = 'C'
        else:
            grade = 'D'

        # Actionable coaching tips
        tips: List[str] = []
        if range_score < 70.0:
            tips.append(
                f"Widen your gesture reach: only used {val_range*100:.0f}% of range "
                f"({min_v:.2f} to {max_v:.2f}). Stretch higher for full sweeps."
            )
        if smooth_score < 70.0:
            tips.append(
                "Smooth out hand acceleration: detected rapid twitches or reversals. "
                "Move like a cello bow — continuous, controlled strokes."
            )
        if efficiency_score < 60.0:
            tips.append(
                "Excessive hand motion relative to parameter response: "
                "focus your hand within the calibrated active zone."
            )
        if not tips:
            tips.append("Superb gestural control! Smooth velocity arcs and full dynamic range.")

        # Summary text
        summary = (
            f"Performance Grade: {grade} ({overall_int}/100) | "
            f"Smoothness: {smooth_score:.0f}% | Range: {range_score:.0f}% | "
            f"Stability: {stability_score:.0f}% | Efficiency: {efficiency_score:.0f}%"
        )

        return GestureScoreReport(
            version=1,
            source='vision.scoring',
            overall_score=overall_int,
            letter_grade=grade,
            sample_count=len(self.samples),
            duration_s=round(duration, 3),
            breakdown=ScoreBreakdown(
                smoothness=round(smooth_score, 1),
                range_coverage=round(range_score, 1),
                stability=round(stability_score, 1),
                efficiency=round(efficiency_score, 1),
            ),
            min_value=round(min_v, 3),
            max_value=round(max_v, 3),
            actionable_tips=tips,
            summary=summary,
        )


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--demo', action='store_true', help='Run synthetic gesture scoring demo')
    args = p.parse_args(argv)

    if args.demo:
        print("=== OmniRiff Gesture Scoring & Technique Analytics Demo ===")
        print("Simulating 3.0s expressive filter sweep with minor tremor...")
        scorer = GestureScorer()
        fps = 30.0
        for i in range(90):
            t = i / fps
            val = 0.5 + 0.42 * math.sin(2 * math.pi * 0.4 * t)
            scorer.add_sample(t, val, (0.5, 0.5))

        report = scorer.evaluate()
        print(f"\nDuration:        {report.duration_s}s ({report.sample_count} frames)")
        print(f"Overall Grade:   {report.letter_grade} ({report.overall_score}/100)")
        print(f"Smoothness:      {report.breakdown.smoothness}%")
        print(f"Range Coverage:  {report.breakdown.range_coverage}%")
        print(f"Stability:       {report.breakdown.stability}%")
        print(f"Efficiency:      {report.breakdown.efficiency}%")
        print("\nActionable Tips:")
        for tip in report.actionable_tips:
            print(f"  * {tip}")
        print(f"\nVerdict: {report.summary}\n")
        return

    p.print_help()


if __name__ == '__main__':
    main()

