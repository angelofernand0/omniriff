"""Air FX Spatial Canvas (Spatial Theremin & 2D Soundpad).

Transforms 2D/3D performance airspace into an expressive soundpad matrix.
Interpolates dual-parameter effects (Filter & Reverb) bilinearly across
four spatial quadrant corners:

    Top-Left (TL):     Cosmic Shimmer   (Filter: 0.95, Reverb: 0.85)
    Top-Right (TR):    Crisp Lead/Bite  (Filter: 0.90, Reverb: 0.10)
    Bottom-Left (BL):  Submerged Wash   (Filter: 0.25, Reverb: 0.75)
    Bottom-Right (BR): Warm Acoustic    (Filter: 0.35, Reverb: 0.05)

Clutching: Open hand arms, pinch engages and drags through the canvas.
Releasing freezes the current sound coordinates in space.
Emits schema-compliant v1 parameter envelopes strictly within 10 pairs/s (20 Hz).
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CornerPreset:
    name: str
    filter_val: float
    reverb_val: float


@dataclass
class CanvasConfig:
    # Physical bounding box in normalized camera frame coordinates
    xmin: float = 0.20
    xmax: float = 0.80
    ymin: float = 0.10  # Top of frame
    ymax: float = 0.50  # Above guitar strum zone

    # Corner Presets
    top_left: CornerPreset = CornerPreset('Cosmic Shimmer', 0.95, 0.85)
    top_right: CornerPreset = CornerPreset('Crisp Bite', 0.90, 0.10)
    bottom_left: CornerPreset = CornerPreset('Submerged Wash', 0.25, 0.75)
    bottom_right: CornerPreset = CornerPreset('Warm Acoustic', 0.35, 0.05)

    pair_rate: float = 10.0   # 10 pairs/sec = 20 events/sec
    tau: float = 0.10         # Smoothing time constant
    deadband: float = 0.015   # Output threshold
    confidence_gate: float = 0.60


class SpatialCanvasController:
    """Calculates continuous bilinear parameter blends from 2D hand coordinates."""

    def __init__(self, config: Optional[CanvasConfig] = None):
        self.config = config or CanvasConfig()
        self.active: bool = False
        self.armed: bool = False

        self.current_filter: Optional[float] = None
        self.current_reverb: Optional[float] = None

        self.sent_filter: Optional[float] = None
        self.sent_reverb: Optional[float] = None
        self.sent_at: float = -math.inf
        self.previous_time: Optional[float] = None
        self.seq: int = 0

    def rearm(self):
        self.active = False
        self.armed = False
        self.current_filter = None
        self.current_reverb = None

    def interpolate(self, x: float, y: float) -> Tuple[float, float, str]:
        """Compute bilinear interpolation of (filter, reverb) from normalized (x, y).

        Returns (filter_value, reverb_value, nearest_quadrant_name).
        """
        cfg = self.config
        # Normalize x into [0, 1] across canvas width
        span_x = max(cfg.xmax - cfg.xmin, 0.05)
        u = min(1.0, max(0.0, (x - cfg.xmin) / span_x))

        # Normalize y into [0, 1] across canvas height (y=ymin is top -> v=1, y=ymax is bottom -> v=0)
        span_y = max(cfg.ymax - cfg.ymin, 0.05)
        v = min(1.0, max(0.0, (cfg.ymax - y) / span_y))

        # Bilinear blending weights
        w_bl = (1.0 - u) * (1.0 - v)
        w_br = u * (1.0 - v)
        w_tl = (1.0 - u) * v
        w_tr = u * v

        filt = (
            w_bl * cfg.bottom_left.filter_val
            + w_br * cfg.bottom_right.filter_val
            + w_tl * cfg.top_left.filter_val
            + w_tr * cfg.top_right.filter_val
        )

        rev = (
            w_bl * cfg.bottom_left.reverb_val
            + w_br * cfg.bottom_right.reverb_val
            + w_tl * cfg.top_left.reverb_val
            + w_tr * cfg.top_right.reverb_val
        )

        # Nearest sector quadrant name
        if v >= 0.5:
            nearest = cfg.top_left.name if u < 0.5 else cfg.top_right.name
        else:
            nearest = cfg.bottom_left.name if u < 0.5 else cfg.bottom_right.name

        return (min(1.0, max(0.0, filt)), min(1.0, max(0.0, rev)), nearest)

    def update(
        self,
        x: Optional[float],
        y: Optional[float],
        pinch: Optional[float],
        confidence: float,
        now: float,
        timestamp_ms: int,
    ) -> List[Dict[str, Any]]:
        """Processes hand position and emits synchronized parameter pairs."""
        if (
            x is None
            or y is None
            or pinch is None
            or not all(math.isfinite(v) for v in (x, y, pinch, confidence, now))
            or not 0 <= confidence <= 1
            or confidence < self.config.confidence_gate
        ):
            self.active = False
            self.armed = False
            self.previous_time = None
            return []

        if self.previous_time is not None and now <= self.previous_time:
            return []

        # Open-then-pinch clutching
        if pinch >= 0.45:
            self.active = False
            self.armed = True
            self.current_filter = None
            self.current_reverb = None
        elif self.armed and not self.active and pinch <= 0.25:
            self.active = True

        dt = 0.0 if self.previous_time is None else now - self.previous_time
        self.previous_time = now

        if not self.active:
            return []

        target_filt, target_rev, _ = self.interpolate(x, y)

        # Exponential smoothing (tau)
        smooth = 1.0 - math.exp(-dt / self.config.tau) if dt > 0 else 1.0
        self.current_filter = (
            target_filt
            if self.current_filter is None
            else self.current_filter + smooth * (target_filt - self.current_filter)
        )
        self.current_reverb = (
            target_rev
            if self.current_reverb is None
            else self.current_reverb + smooth * (target_rev - self.current_reverb)
        )

        # Rate check
        if now - self.sent_at < (1.0 / self.config.pair_rate):
            return []

        # Deadband check
        diff_f = abs(self.current_filter - self.sent_filter) if self.sent_filter is not None else math.inf
        diff_r = abs(self.current_reverb - self.sent_reverb) if self.sent_reverb is not None else math.inf

        if diff_f < self.config.deadband and diff_r < self.config.deadband:
            return []

        events = [
            {
                'version': 1,
                'source': 'vision',
                'seq': self.seq,
                'timestamp_ms': timestamp_ms,
                'type': 'parameter',
                'control': 'filter',
                'value': round(self.current_filter, 4),
                'confidence': confidence,
            },
            {
                'version': 1,
                'source': 'vision',
                'seq': self.seq + 1,
                'timestamp_ms': timestamp_ms,
                'type': 'parameter',
                'control': 'reverb',
                'value': round(self.current_reverb, 4),
                'confidence': confidence,
            },
        ]
        self.seq += 2
        self.sent_at = now
        self.sent_filter = self.current_filter
        self.sent_reverb = self.current_reverb
        return events

    def render_ascii_radar(self, x: float, y: float, width: int = 15, height: int = 7) -> str:
        """Render a high-contrast ASCII radar of where the hand is in the 2D FX space."""
        cfg = self.config
        span_x = max(cfg.xmax - cfg.xmin, 0.05)
        span_y = max(cfg.ymax - cfg.ymin, 0.05)
        u = min(1.0, max(0.0, (x - cfg.xmin) / span_x))
        v = min(1.0, max(0.0, (y - cfg.ymin) / span_y))

        px = int(round(u * (width - 1)))
        py = int(round(v * (height - 1)))

        lines = []
        for r in range(height):
            row = []
            for c in range(width):
                if r == py and c == px:
                    row.append('●')
                elif (r == 0 or r == height - 1) and (c == 0 or c == width - 1):
                    row.append('+')
                elif r == height // 2 or c == width // 2:
                    row.append('·')
                else:
                    row.append(' ')
            lines.append(''.join(row))
        return '\n'.join(lines)


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--demo', action='store_true', help='Demonstrate 2D spatial canvas traversal')
    args = p.parse_args(argv)

    if args.demo:
        print("=== OmniRiff Air FX Spatial Canvas Demo ===")
        print("Simulating circular hand trajectory through 4 spatial sound quadrants:")
        print("  TL: Cosmic Shimmer  | TR: Crisp Bite")
        print("  BL: Submerged Wash  | BR: Warm Acoustic\n")

        ctrl = SpatialCanvasController()
        # Arm & engage
        ctrl.update(0.5, 0.3, 0.5, 0.95, 0.0, 0)
        ctrl.update(0.5, 0.3, 0.2, 0.95, 0.05, 50)

        t = 0.10
        emitted = 0
        quadrants_seen = set()

        for step in range(24):
            angle = (step / 24.0) * 2 * math.pi
            # Circular path centered at (0.5, 0.3) with radius rx=0.25, ry=0.15
            x = 0.50 + 0.25 * math.cos(angle)
            y = 0.30 + 0.15 * math.sin(angle)
            filt, rev, quad = ctrl.interpolate(x, y)
            quadrants_seen.add(quad)

            evs = ctrl.update(x, y, 0.2, 0.95, t, int(t * 1000))
            if evs:
                emitted += len(evs)
                print(f"  t={t:.2f}s | (x={x:.2f}, y={y:.2f}) -> [{quad:^16}] "
                      f"Filter={evs[0]['value']:.2f}, Reverb={evs[1]['value']:.2f}")
            t += 0.05

        print(f"\nResult: Visited {len(quadrants_seen)} sound quadrants ({', '.join(sorted(quadrants_seen))})")
        print(f"Emitted: {emitted} schema-compliant parameter events ({emitted/t:.1f} events/sec)\n")
        print("Final Spatial Radar:")
        print(ctrl.render_ascii_radar(0.5, 0.3))
        return

    p.print_help()


if __name__ == '__main__':
    main()
