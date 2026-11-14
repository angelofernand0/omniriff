"""Gesture-Modulated Rhythmic LFO & Tempo-Synced Arpeggiator (vision/lfo.py).

Provides beat-synchronized parameter modulation (auto-wah, rhythmic tremolo chop,
tempo-locked filter sweeps) controlled dynamically by physical hand gestures:
  - Elevation (Y-axis): Selects musical tempo subdivisions (1/1, 1/2, 1/4, 1/8, 1/16)
  - Knuckle Tilt / Pinch Depth: Modulates LFO depth (0.0 = static, 1.0 = full sweep)
  - Waveforms: Sine (smooth vibrato), Triangle (wah), Square (killswitch chop), Saw (filter plucks)

Synchronizes with tempo from Coach Ears/Eyes or user-configured BPM.
Strictly rate-limited to <= 20 events/s to comply with the transport budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import time
from typing import Any, Dict, List, Optional, Tuple


class LFOWaveform(str, Enum):
    SINE = 'sine'
    TRIANGLE = 'triangle'
    SQUARE = 'square'
    SAW = 'saw'


# Musical beat subdivisions and their note length relative to a quarter note (1 beat)
SUBDIVISIONS = [
    ('1/1', 4.0),     # Whole note
    ('1/2', 2.0),     # Half note
    ('1/4', 1.0),     # Quarter note
    ('1/8', 0.5),     # Eighth note
    ('1/16', 0.25),   # Sixteenth note
    ('1/32', 0.125),  # Thirty-second note
]


@dataclass
class LFOConfig:
    bpm: float = 120.0
    waveform: LFOWaveform = LFOWaveform.SINE
    control: str = 'filter'
    base_center: float = 0.50     # Midpoint around which LFO oscillates
    max_rate_hz: float = 20.0     # Max UDP emission rate
    confidence_gate: float = 0.60
    deadband: float = 0.015


class GestureLFO:
    """Stateful tempo-locked LFO driven by hand height and tilt."""

    def __init__(self, config: Optional[LFOConfig] = None):
        self.config = config or LFOConfig()
        if self.config.bpm <= 0 or not math.isfinite(self.config.bpm):
            raise ValueError('BPM must be positive and finite')

        self.phase: float = 0.0
        self.last_time: Optional[float] = None
        self.active: bool = False
        self.armed: bool = False

        self.current_subdivision: str = '1/4'
        self.current_freq_hz: float = 2.0
        self.current_depth: float = 0.5
        self.current_val: float = self.config.base_center

        self.sent_at: float = -math.inf
        self.sent_val: Optional[float] = None
        self.seq: int = 0

    def set_bpm(self, bpm: float):
        if math.isfinite(bpm) and bpm > 0:
            self.config.bpm = bpm

    def calculate_subdivision(self, y: float) -> Tuple[str, float]:
        """Maps normalized elevation y in [0.8, 0.2] to musical subdivisions.

        Bottom (y >= 0.7) -> 1/1 (slow whole note)
        Top (y <= 0.25)   -> 1/32 (rapid chop)
        """
        # Invert so higher elevation = faster rate
        clamped_y = min(0.80, max(0.20, y))
        norm = (0.80 - clamped_y) / 0.60  # 0.0 at bottom, 1.0 at top
        idx = int(round(norm * (len(SUBDIVISIONS) - 1)))
        idx = min(len(SUBDIVISIONS) - 1, max(0, idx))

        name, beats = SUBDIVISIONS[idx]
        # Frequency = beats per second / note length in beats
        freq_hz = (self.config.bpm / 60.0) / beats
        return (name, freq_hz)

    def compute_wave(self, phase: float, form: LFOWaveform) -> float:
        """Compute normalized bipolar wave value in [-1.0, +1.0] for phase in [0, 2*pi)."""
        p = phase % (2.0 * math.pi)

        if form == LFOWaveform.SINE:
            return math.sin(p)
        elif form == LFOWaveform.TRIANGLE:
            # Linear triangle wave
            fraction = p / (2.0 * math.pi)
            if fraction < 0.25:
                return 4.0 * fraction
            elif fraction < 0.75:
                return 2.0 - 4.0 * fraction
            else:
                return -4.0 + 4.0 * fraction
        elif form == LFOWaveform.SQUARE:
            # Bipolar square wave
            return 1.0 if p < math.pi else -1.0
        elif form == LFOWaveform.SAW:
            # Downward sawtooth
            return 1.0 - 2.0 * (p / (2.0 * math.pi))
        return 0.0

    def update(
        self,
        y: Optional[float],
        pinch: Optional[float],
        tilt_depth: float,
        confidence: float,
        now: float,
        timestamp_ms: int,
    ) -> Optional[Dict[str, Any]]:
        """Advance LFO phase and return protocol-compliant parameter event if ready."""
        if (
            y is None
            or pinch is None
            or not all(math.isfinite(v) for v in (y, pinch, tilt_depth, confidence, now))
            or confidence < self.config.confidence_gate
        ):
            self.active = False
            self.armed = False
            self.last_time = None
            return None

        if self.last_time is not None and now <= self.last_time:
            return None

        dt = 0.0 if self.last_time is None else now - self.last_time
        self.last_time = now

        # Clutching
        if pinch >= 0.45:
            self.active = False
            self.armed = True
        elif self.armed and not self.active and pinch <= 0.25:
            self.active = True

        if not self.active:
            return None

        # Compute rate subdivision and depth
        subdiv_name, freq_hz = self.calculate_subdivision(y)
        self.current_subdivision = subdiv_name
        self.current_freq_hz = freq_hz
        self.current_depth = min(1.0, max(0.0, float(tilt_depth)))

        # Advance continuous phase accumulator
        self.phase = (self.phase + 2.0 * math.pi * self.current_freq_hz * dt) % (2.0 * math.pi)

        # Compute output parameter value
        wave_val = self.compute_wave(self.phase, self.config.waveform)
        # Modulate around base_center
        val = self.config.base_center + (self.current_depth * 0.48) * wave_val
        self.current_val = min(1.0, max(0.0, val))

        # Rate limiter
        if now - self.sent_at < (1.0 / self.config.max_rate_hz):
            return None

        # Deadband
        if self.sent_val is not None and abs(self.current_val - self.sent_val) < self.config.deadband:
            return None

        event = {
            'version': 1,
            'source': 'vision',
            'seq': self.seq,
            'timestamp_ms': timestamp_ms,
            'type': 'parameter',
            'control': self.config.control,
            'value': round(self.current_val, 4),
            'confidence': confidence,
        }
        self.seq += 1
        self.sent_at = now
        self.sent_val = self.current_val
        return event


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--demo', action='store_true', help='Demonstrate rhythmic LFO sweep')
    p.add_argument('--bpm', type=float, default=120.0, help='Base tempo in BPM')
    p.add_argument('--waveform', choices=['sine', 'triangle', 'square', 'saw'], default='square')
    args = p.parse_args(argv)

    if args.demo:
        print(f"=== OmniRiff Gesture Rhythmic LFO Demo ({args.bpm:.0f} BPM, {args.waveform.upper()}) ===")
        print("Simulating hand elevating from bottom (1/1 whole note) to top (1/16 note):")
        cfg = LFOConfig(bpm=args.bpm, waveform=LFOWaveform(args.waveform))
        lfo = GestureLFO(cfg)

        # Arm & engage
        lfo.update(0.7, 0.5, 0.8, 0.9, 0.0, 0)
        lfo.update(0.7, 0.2, 0.8, 0.9, 0.05, 50)

        t = 0.10
        emitted = 0
        subdivs_seen = []

        for i in range(25):
            # Elevate hand from 0.75 down to 0.22
            y = 0.75 - (i / 25.0) * 0.50
            ev = lfo.update(y, 0.2, 0.9, 0.95, t, int(t * 1000))
            if ev:
                emitted += 1
                bar_len = int(round(ev['value'] * 20))
                bar = '█' * bar_len + '░' * (20 - bar_len)
                print(f"  t={t:.2f}s | Subdiv: {lfo.current_subdivision:>4} ({lfo.current_freq_hz:4.1f} Hz) | "
                      f"Val: {ev['value']:.2f} [{bar}]")
                if lfo.current_subdivision not in subdivs_seen:
                    subdivs_seen.append(lfo.current_subdivision)
            t += 0.05

        print(f"\nResult: Progressed through tempo subdivisions: {' -> '.join(subdivs_seen)}")
        print(f"Emitted {emitted} rhythmic control envelopes within 20 Hz budget.")
        return

    p.print_help()


if __name__ == '__main__':
    main()
