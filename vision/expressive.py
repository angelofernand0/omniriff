"""3D Hand orientation and dual-axis gesture control within 20 Hz shared budget."""
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class OrientationResult:
    roll_deg: float         # Knuckle line angle relative to horizontal (-90 to +90 deg)
    pitch_deg: float        # Palm line angle relative to vertical (-90 to +90 deg)
    tilt_amount: float      # Normalized absolute roll magnitude in [0, 1] (0 deg -> 0, 60+ deg -> 1.0)
    openness: float         # Hand openness ratio in [0, 1]


def compute_hand_orientation(
    landmarks: List[Any],
    width: float = 1.0,
    height: float = 1.0,
) -> Optional[OrientationResult]:
    """Calculate 3D orientation angles from 21 MediaPipe hand landmarks.

    Defaults to normalized coordinate space (width=1.0, height=1.0). Pixel
    dimensions can be passed to account for non-square pixel sensor aspect.
    """
    if not landmarks or len(landmarks) < 21:
        return None

    def get_pt(idx):
        p = landmarks[idx]
        if hasattr(p, 'x') and hasattr(p, 'y'):
            z = getattr(p, 'z', 0.0)
            return p.x * width, p.y * height, z * width
        return p[0] * width, p[1] * height, (p[2] * width if len(p) > 2 else 0.0)

    try:
        w_x, w_y, _ = get_pt(0)   # Wrist
        i_x, i_y, _ = get_pt(5)   # Index MCP
        m_x, m_y, _ = get_pt(9)   # Middle MCP
        p_x, p_y, _ = get_pt(17)  # Pinky MCP

        # Knuckle line vector from Index MCP to Pinky MCP
        dx_k = p_x - i_x
        dy_k = p_y - i_y
        k_dist = math.hypot(dx_k, dy_k)
        if k_dist < 1e-4:
            return None

        # Roll angle: angle of knuckle line relative to horizontal
        angle_rad = math.atan2(dy_k, dx_k)
        roll_deg = math.degrees(angle_rad)

        # Normalize roll to range [-90, +90]
        while roll_deg > 90:
            roll_deg -= 180
        while roll_deg < -90:
            roll_deg += 180

        # Tilt amount: 0 at horizontal (neutral), scaling smoothly up to 1.0 at 60 degrees
        tilt_amount = min(1.0, max(0.0, abs(roll_deg) / 60.0))

        # Pitch angle: vector from wrist to middle MCP relative to vertical
        dx_p = m_x - w_x
        dy_p = m_y - w_y
        pitch_rad = math.atan2(dx_p, -dy_p)  # 0 when pointing straight up (negative Y)
        pitch_deg = math.degrees(pitch_rad)
        while pitch_deg > 90:
            pitch_deg -= 180
        while pitch_deg < -90:
            pitch_deg += 180

        # Hand openness: distance between wrist (0) and middle fingertip (12) normalized by palm scale (0 to 9)
        tip_x, tip_y, _ = get_pt(12)
        palm_scale = math.hypot(dx_p, dy_p)
        hand_span = math.hypot(tip_x - w_x, tip_y - w_y)
        openness = min(1.0, max(0.0, (hand_span / max(palm_scale, 1e-4) - 1.0) / 1.2))

        return OrientationResult(
            roll_deg=roll_deg,
            pitch_deg=pitch_deg,
            tilt_amount=tilt_amount,
            openness=openness,
        )
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return None


class DualAxisController:
    """Combines Y elevation (Primary) and Hand Tilt Roll (Secondary) into two synchronized parameters.

    - Primary (Elevation): Filter Cutoff (or Scene Morph amount)
    - Secondary (Tilt/Roll): Reverb Wetness / Ambience Depth
    Emits schema-compliant v1 parameter envelopes over UDP with monotonic sequencing.
    The default pair rate is 10 Hz (20 events/sec total), strictly respecting the transport budget.
    """

    def __init__(
        self,
        low: float = 0.8,
        high: float = 0.2,
        pair_rate: float = 10.0,
        confidence: float = 0.6,
        deadband: float = 0.015,
        tau: float = 0.12,
        primary_control: str = 'filter',
        secondary_control: str = 'reverb',
    ):
        if not all(math.isfinite(x) for x in (low, high, pair_rate, confidence, deadband, tau)):
            raise ValueError('configuration must be finite')
        if not 0 <= high < low <= 1 or low - high < 0.05:
            raise ValueError('calibration needs separated high and low positions in [0,1]')
        if not 0 < pair_rate <= 30 or not 0 <= confidence <= 1 or not 0 <= deadband < 1 or tau <= 0:
            raise ValueError('invalid pair_rate, confidence, deadband or smoothing')
        if primary_control not in ('filter', 'reverb') or secondary_control not in ('filter', 'reverb'):
            raise ValueError('unsupported controls')
        if primary_control == secondary_control:
            raise ValueError('primary and secondary controls must be distinct')

        self.low = low
        self.high = high
        self.pair_rate = pair_rate
        self.confidence = confidence
        self.deadband = deadband
        self.tau = tau
        self.primary_control = primary_control
        self.secondary_control = secondary_control

        self.active = False
        self.armed = False
        self.primary_val: Optional[float] = None
        self.secondary_val: Optional[float] = None
        self.sent_primary: Optional[float] = None
        self.sent_secondary: Optional[float] = None
        self.sent_at = -math.inf
        self.previous_time: Optional[float] = None
        self.seq = 0

    def rearm(self):
        self.active = self.armed = False
        self.primary_val = self.secondary_val = None
        self.sent_primary = self.sent_secondary = None
        self.previous_time = None

    def update(
        self,
        y: Optional[float],
        pinch: Optional[float],
        orientation: Optional[OrientationResult],
        confidence: float,
        now: float,
        timestamp_ms: int,
    ) -> List[Dict[str, Any]]:
        """Processes dual-axis hand motion and returns list of 0, 1, or 2 parameter events."""
        if (
            y is None
            or pinch is None
            or not all(math.isfinite(v) for v in (y, pinch, confidence, now))
            or not 0 <= confidence <= 1
            or confidence < self.confidence
        ):
            self.active = self.armed = False
            self.previous_time = None
            self.primary_val = self.secondary_val = None
            return []

        if self.previous_time is not None and now <= self.previous_time:
            return []

        # Open-then-pinch clutching logic (matches Controller)
        if pinch >= 0.45:
            self.active = False
            self.armed = True
            self.primary_val = self.secondary_val = None
        elif self.armed and not self.active and pinch <= 0.25:
            self.active = True

        dt = 0.0 if self.previous_time is None else now - self.previous_time
        self.previous_time = now

        if not self.active:
            return []

        # Target primary (Elevation)
        target_p = min(1.0, max(0.0, (self.low - y) / (self.low - self.high)))

        # Target secondary (Hand Roll Tilt Amount)
        target_s = orientation.tilt_amount if orientation else 0.0
        target_s = min(1.0, max(0.0, target_s))

        # Exponential smoothing (tau)
        smooth_factor = 1.0 - math.exp(-dt / self.tau) if dt > 0 else 1.0
        self.primary_val = target_p if self.primary_val is None else self.primary_val + smooth_factor * (target_p - self.primary_val)
        self.secondary_val = target_s if self.secondary_val is None else self.secondary_val + smooth_factor * (target_s - self.secondary_val)

        # Rate limiter check (pair_rate pairs/sec)
        if now - self.sent_at < (1.0 / self.pair_rate):
            return []

        events = []

        # Check deadband for primary and secondary
        p_diff = abs(self.primary_val - self.sent_primary) if self.sent_primary is not None else math.inf
        s_diff = abs(self.secondary_val - self.sent_secondary) if self.sent_secondary is not None else math.inf

        # Emit if either has moved beyond deadband
        if p_diff >= self.deadband or s_diff >= self.deadband:
            ev_p = {
                'version': 1,
                'source': 'vision',
                'seq': self.seq,
                'timestamp_ms': timestamp_ms,
                'type': 'parameter',
                'control': self.primary_control,
                'value': self.primary_val,
                'confidence': confidence,
            }
            self.seq += 1
            events.append(ev_p)
            self.sent_primary = self.primary_val

            ev_s = {
                'version': 1,
                'source': 'vision',
                'seq': self.seq,
                'timestamp_ms': timestamp_ms,
                'type': 'parameter',
                'control': self.secondary_control,
                'value': self.secondary_val,
                'confidence': confidence,
            }
            self.seq += 1
            events.append(ev_s)
            self.sent_secondary = self.secondary_val

            self.sent_at = now

        return events
