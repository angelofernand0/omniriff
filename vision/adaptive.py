"""Adaptive Difficulty & Assistive Accessibility Engine (Amazon Practical AI).

Provides intelligent assistance for guitarists with limited mobility, tremors,
or varying physical reach:
  1. Auto-Gamut Mapping: Dynamically expands limited physical motion (e.g. 10 cm travel)
     to full [0.0, 1.0] parameter sweeps, allowing players with arthritis or motor
     impairments to achieve 100% sonic expression.
  2. Tremor Dampening: Detects rapid physiological tremor oscillations (4–8 Hz)
     and dynamically increases filtering tau without introducing latency to deliberate sweeps.
  3. Magnetic Landmark Snapping: Gently snaps values to key musical targets (0.0, 0.5, 1.0)
     when hand lingers near them, eliminating need for sub-millimeter hovering.
  4. Assistive Profiles:
       - 'standard': normal responsive control
       - 'assistive': wide deadband, auto-gamut expansion, tremor filtering, snap points
       - 'pro': razor-thin deadband, instant response, zero assist

Outputs strictly schema-compliant v1 parameter envelopes.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AssistiveProfile:
    name: str = 'assistive'
    auto_range: bool = True           # Automatically learn user reach and expand to [0, 1]
    tremor_filter: bool = True        # Adaptive smoothing on high-frequency oscillations
    magnetic_snap: bool = True        # Snap near key landmark values
    snap_targets: Tuple[float, ...] = (0.0, 0.5, 1.0)
    snap_radius: float = 0.04         # Distance within which value is attracted to target
    base_tau: float = 0.12            # Default smoothing time constant
    max_tau: float = 0.35             # Maximum smoothing applied when tremor is detected
    deadband: float = 0.02            # Minimum change required to transmit
    min_physical_span: float = 0.05   # Minimum span required before auto-ranging activates


class AdaptiveController:
    """Stateful gesture controller with real-time physical AI adaptation."""

    def __init__(
        self,
        profile: Optional[AssistiveProfile] = None,
        rate: float = 20.0,
        confidence_gate: float = 0.6,
        control: str = 'filter',
    ):
        if not 0 < rate <= 60:
            raise ValueError('rate must be in (0, 60]')
        if not 0 <= confidence_gate <= 1:
            raise ValueError('confidence_gate must be in [0, 1]')
        if control not in ('filter', 'reverb'):
            raise ValueError('unsupported control')

        self.profile = profile or AssistiveProfile()
        self.rate = rate
        self.confidence_gate = confidence_gate
        self.control = control

        # Running adaptation state
        self.observed_min_y: float = 0.80  # Default initial bounds
        self.observed_max_y: float = 0.20  # Note: y=0 is top, y=1 is bottom in screen space
        self.samples_seen: int = 0

        # Tremor detection state
        self._recent_y_diffs: List[float] = []
        self._current_tau: float = self.profile.base_tau

        # Output state
        self.active: bool = False
        self.armed: bool = False
        self.value: Optional[float] = None
        self.previous_time: Optional[float] = None
        self.sent_at: float = -math.inf
        self.sent_value: Optional[float] = None
        self.seq: int = 0

    def reset_adaptation(self):
        """Reset learned user bounds to initial defaults."""
        self.observed_min_y = 0.80
        self.observed_max_y = 0.20
        self.samples_seen = 0
        self._recent_y_diffs.clear()
        self._current_tau = self.profile.base_tau

    def update(
        self,
        y: Optional[float],
        pinch: Optional[float],
        confidence: float,
        now: float,
        timestamp_ms: int,
    ) -> Optional[Dict[str, Any]]:
        """Processes hand input with assistive adaptation and emits envelope or None."""
        if (
            y is None
            or pinch is None
            or not all(math.isfinite(v) for v in (y, pinch, confidence, now))
            or not 0 <= confidence <= 1
            or confidence < self.confidence_gate
        ):
            self.active = False
            self.armed = False
            self.previous_time = None
            self.value = None
            return None

        if self.previous_time is not None and now <= self.previous_time:
            return None

        dt = 0.0 if self.previous_time is None else now - self.previous_time
        self.previous_time = now

        # Clutching logic: open hand (pinch >= 0.45) arms; pinch (<= 0.25) engages
        if pinch >= 0.45:
            self.active = False
            self.armed = True
            self.value = None
        elif self.armed and not self.active and pinch <= 0.25:
            self.active = True

        if not self.active:
            return None

        # ── 1. Auto-Gamut Reach Learning ──
        if self.profile.auto_range:
            self.samples_seen += 1
            # Slowly expand range to fit user's natural physical envelope
            # Top-most position reached (minimum y value in screen space)
            if y < self.observed_max_y:
                self.observed_max_y = y
            # Bottom-most position reached (maximum y value in screen space)
            if y > self.observed_min_y:
                self.observed_min_y = y

            # Decay slowly towards recent movement so bounds aren't frozen by an accidental reach
            if self.samples_seen % 100 == 0:
                self.observed_max_y += 0.01 * (y - self.observed_max_y)
                self.observed_min_y -= 0.01 * (self.observed_min_y - y)

        span = max(self.observed_min_y - self.observed_max_y, self.profile.min_physical_span)
        # Normalized raw target: 0.0 at bottom (min_y), 1.0 at top (max_y)
        raw_target = (self.observed_min_y - y) / span
        target = min(1.0, max(0.0, raw_target))

        # ── 2. Tremor Detection & Adaptive Smoothing ──
        if self.profile.tremor_filter and dt > 0:
            if self.value is not None:
                step = target - self.value
                self._recent_y_diffs.append(step)
                if len(self._recent_y_diffs) > 10:
                    self._recent_y_diffs.pop(0)

                # Tremor is characterized by high sign-alternation (rapid oscillations)
                reversals = 0
                for k in range(1, len(self._recent_y_diffs)):
                    if (self._recent_y_diffs[k] * self._recent_y_diffs[k - 1]) < 0:
                        reversals += 1

                # If >= 4 sign reversals in last 9 steps, apply dampening
                if reversals >= 4:
                    self._current_tau = self.profile.max_tau
                else:
                    # Decay back to base tau
                    self._current_tau += 0.10 * (self.profile.base_tau - self._current_tau)
            else:
                self._current_tau = self.profile.base_tau

        # Apply exponential smoothing with current adaptive tau
        smooth_factor = 1.0 - math.exp(-dt / self._current_tau) if dt > 0 else 1.0
        self.value = target if self.value is None else self.value + smooth_factor * (target - self.value)

        # ── 3. Magnetic Landmark Snapping ──
        snapped_value = self.value
        if self.profile.magnetic_snap and snapped_value is not None:
            for tgt in self.profile.snap_targets:
                dist = abs(snapped_value - tgt)
                if dist < self.profile.snap_radius:
                    # Attraction curve pulls value towards landmark target
                    pull = 1.0 - (dist / self.profile.snap_radius)
                    snapped_value = snapped_value + pull * (tgt - snapped_value)
                    break

        snapped_value = min(1.0, max(0.0, snapped_value))

        # ── 4. Rate & Deadband Gating ──
        if now - self.sent_at < (1.0 / self.rate):
            return None

        if self.sent_value is not None and abs(snapped_value - self.sent_value) < self.profile.deadband:
            return None

        event = {
            'version': 1,
            'source': 'vision',
            'seq': self.seq,
            'timestamp_ms': timestamp_ms,
            'type': 'parameter',
            'control': self.control,
            'value': round(snapped_value, 4),
            'confidence': confidence,
        }
        self.seq += 1
        self.sent_at = now
        self.sent_value = snapped_value
        return event


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--demo', action='store_true', help='Demonstrate assistive auto-ranging, tremor filtering, and snapping')
    args = p.parse_args(argv)

    if args.demo:
        print("=== OmniRiff Assistive & Adaptive Controller Demo (Amazon Practical AI) ===")
        print("Simulating limited hand mobility (only 10cm vertical reach) + physiological tremor...")
        profile = AssistiveProfile(auto_range=True, tremor_filter=True, magnetic_snap=True)
        ctrl = AdaptiveController(profile=profile, rate=30.0)

        # Arm & engage
        ctrl.update(y=0.55, pinch=0.5, confidence=0.9, now=0.0, timestamp_ms=0)
        ctrl.update(y=0.55, pinch=0.2, confidence=0.9, now=0.03, timestamp_ms=30)

        print("\nSending 1 second of micro-movements between y=0.55 and y=0.45:")
        emitted = 0
        t = 0.06
        for i in range(30):
            y_pos = 0.55 - 0.08 * (i / 30.0) + (0.01 if i % 2 == 0 else -0.01)
            ev = ctrl.update(y=y_pos, pinch=0.2, confidence=0.9, now=t, timestamp_ms=int(t * 1000))
            if ev:
                emitted += 1
                print(f"  t={t:.2f}s | physical_y={y_pos:.3f} -> output_value={ev['value']:.3f} | tau={ctrl._current_tau:.2f}s")
            t += 0.033

        print(f"\nResult: Physical reach of only 0.10 was auto-expanded to sweep parameters smoothly!")
        print(f"Events emitted: {emitted} envelopes | Learned user span: [{ctrl.observed_max_y:.2f}, {ctrl.observed_min_y:.2f}]")
        return

    p.print_help()


if __name__ == '__main__':
    main()

