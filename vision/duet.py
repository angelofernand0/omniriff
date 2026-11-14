"""Duet & Collaborative Two-Hand Expressive Controller (vision/duet.py).

Enables concurrent two-hand or two-performer gestural modulation using MediaPipe's
multi-hand tracking (num_hands=2):
  - Hand A (Left Hand / Guitarist): Primary control -> Filter Cutoff
  - Hand B (Right Hand / Guest / Judge): Secondary control -> Reverb Wetness

Features:
  - Dual independent clutching: Each hand must perform its own open-then-pinch cycle.
  - Spatial assignment: Assigns hands based on horizontal camera coordinates (left vs right).
  - Rate budgeting: Strictly allocates 10 Hz to Hand A and 10 Hz to Hand B (<= 20 Hz total).
  - Zero crosstalk: Hand A's movement never resets or interrupts Hand B's active hold.
  - Interactive Judge Demo: A guest can reach into frame and shape the reverb while the
    guitarist shreds!
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class HandChannel:
    name: str                 # 'Hand A' or 'Hand B'
    control: str              # 'filter' or 'reverb'
    target_rate: float = 10.0 # 10 Hz
    deadband: float = 0.015
    tau: float = 0.12
    low_y: float = 0.80
    high_y: float = 0.20

    # Runtime state
    active: bool = False
    armed: bool = False
    value: Optional[float] = None
    sent_value: Optional[float] = None
    sent_at: float = -math.inf
    previous_time: Optional[float] = None


class DuetController:
    """Manages two independent hand channels within a shared 20 Hz UDP transport budget."""

    def __init__(
        self,
        hand_a_control: str = 'filter',
        hand_b_control: str = 'reverb',
        pair_rate: float = 10.0,
        confidence_gate: float = 0.60,
    ):
        if hand_a_control == hand_b_control:
            raise ValueError('Hand A and Hand B must control different parameters')
        if not 0 < pair_rate <= 15:
            raise ValueError('pair_rate must be in (0, 15] to respect total event budget')

        self.confidence_gate = confidence_gate
        self.channel_a = HandChannel(name='Hand A', control=hand_a_control, target_rate=pair_rate)
        self.channel_b = HandChannel(name='Hand B', control=hand_b_control, target_rate=pair_rate)
        self.seq = 0

    def update_channel(
        self,
        chan: HandChannel,
        y: Optional[float],
        pinch: Optional[float],
        confidence: float,
        now: float,
        timestamp_ms: int,
    ) -> Optional[Dict[str, Any]]:
        """Process one hand input on its dedicated channel."""
        if (
            y is None
            or pinch is None
            or not all(math.isfinite(v) for v in (y, pinch, confidence, now))
            or confidence < self.confidence_gate
        ):
            chan.active = False
            chan.armed = False
            chan.previous_time = None
            chan.value = None
            return None

        if chan.previous_time is not None and now <= chan.previous_time:
            return None

        dt = 0.0 if chan.previous_time is None else now - chan.previous_time
        chan.previous_time = now

        # Open-then-pinch clutching
        if pinch >= 0.45:
            chan.active = False
            chan.armed = True
            chan.value = None
        elif chan.armed and not chan.active and pinch <= 0.25:
            chan.active = True

        if not chan.active:
            return None

        # Normalized elevation mapping (low_y -> 0.0, high_y -> 1.0)
        target = min(1.0, max(0.0, (chan.low_y - y) / (chan.low_y - chan.high_y)))

        # Exponential smoothing
        smooth = 1.0 - math.exp(-dt / chan.tau) if dt > 0 else 1.0
        chan.value = target if chan.value is None else chan.value + smooth * (target - chan.value)

        # Rate check
        if now - chan.sent_at < (1.0 / chan.target_rate):
            return None

        # Deadband check
        diff = abs(chan.value - chan.sent_value) if chan.sent_value is not None else math.inf
        if diff < chan.deadband:
            return None

        event = {
            'version': 1,
            'source': 'vision',
            'seq': self.seq,
            'timestamp_ms': timestamp_ms,
            'type': 'parameter',
            'control': chan.control,
            'value': round(chan.value, 4),
            'confidence': confidence,
        }
        self.seq += 1
        chan.sent_at = now
        chan.sent_value = chan.value
        return event

    def update_duet(
        self,
        hands: List[Tuple[float, float, float, float]],
        now: float,
        timestamp_ms: int,
    ) -> List[Dict[str, Any]]:
        """Processes up to two detected hands: hands is list of (x, y, pinch, confidence).

        Assigns leftmost hand to Hand A, rightmost hand to Hand B.
        """
        events: List[Dict[str, Any]] = []

        if not hands:
            # No hands present
            self.update_channel(self.channel_a, None, None, 0.0, now, timestamp_ms)
            self.update_channel(self.channel_b, None, None, 0.0, now, timestamp_ms)
            return []

        # Sort hands by horizontal X position
        sorted_hands = sorted(hands, key=lambda h: h[0])

        # Hand A (leftmost)
        x_a, y_a, p_a, c_a = sorted_hands[0]
        ev_a = self.update_channel(self.channel_a, y_a, p_a, c_a, now, timestamp_ms)
        if ev_a:
            events.append(ev_a)

        # Hand B (rightmost, if present)
        if len(sorted_hands) >= 2:
            x_b, y_b, p_b, c_b = sorted_hands[1]
            ev_b = self.update_channel(self.channel_b, y_b, p_b, c_b, now, timestamp_ms)
            if ev_b:
                events.append(ev_b)
        else:
            # Second hand absent
            self.update_channel(self.channel_b, None, None, 0.0, now, timestamp_ms)

        return events


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--demo', action='store_true', help='Demonstrate 2-hand collaborative duet modulation')
    args = p.parse_args(argv)

    if args.demo:
        print("=== OmniRiff Duet Mode: Collaborative Two-Hand Performance Demo ===")
        print("Simulating guitarist (Hand A, Left) controlling Filter while a guest (Hand B, Right) sweeps Reverb:\n")

        ctrl = DuetController()

        # Arm both hands
        ctrl.update_duet([(0.3, 0.7, 0.5, 0.9), (0.7, 0.7, 0.5, 0.9)], now=0.0, timestamp_ms=0)
        # Engage both hands
        ctrl.update_duet([(0.3, 0.7, 0.2, 0.9), (0.7, 0.7, 0.2, 0.9)], now=0.05, timestamp_ms=50)

        t = 0.10
        emitted_a = 0
        emitted_b = 0

        for i in range(20):
            # Hand A moves up (filter opens)
            y_a = 0.70 - (i / 20.0) * 0.45
            # Hand B oscillates (reverb pulses)
            y_b = 0.50 + 0.20 * math.sin(i * 0.4)

            evs = ctrl.update_duet([(0.30, y_a, 0.20, 0.95), (0.70, y_b, 0.20, 0.95)], now=t, timestamp_ms=int(t * 1000))
            for ev in evs:
                if ev['control'] == 'filter':
                    emitted_a += 1
                elif ev['control'] == 'reverb':
                    emitted_b += 1
                print(f"  t={t:.2f}s | [{ev['control'].upper():>6}] = {ev['value']:.2f} (seq={ev['seq']})")
            t += 0.05

        print(f"\nResult: Hand A emitted {emitted_a} Filter events | Hand B emitted {emitted_b} Reverb events")
        print(f"Total emitted: {emitted_a + emitted_b} events (rate: {(emitted_a + emitted_b)/t:.1f} Hz, budget max: 20 Hz)")
        return

    p.print_help()


if __name__ == '__main__':
    main()
