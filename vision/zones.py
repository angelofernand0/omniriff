"""Spatial performance zones and strum-guard protection for guitarists."""
import math
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Rect:
    ymin: float
    xmin: float
    ymax: float
    xmax: float

    def __post_init__(self):
        for name, val in (('ymin', self.ymin), ('xmin', self.xmin), ('ymax', self.ymax), ('xmax', self.xmax)):
            if not isinstance(val, (int, float)) or not math.isfinite(val) or not 0 <= val <= 1:
                raise ValueError(f'{name} must be finite number in [0, 1]')
        if self.ymin >= self.ymax or self.xmin >= self.xmax:
            raise ValueError('invalid rect bounds: min must be strictly less than max')

    def contains(self, x: float, y: float) -> bool:
        return self.xmin <= x <= self.xmax and self.ymin <= y <= self.ymax


class StrumGuard:
    """Protects against accidental gesture triggers while strumming or picking.

    When the player's hand is inside the designated guitar strum zone, or
    when rapid oscillatory strumming motion is detected, gesture activation
    is suppressed so holding a pick (a pinch gesture) never sweeps effects.
    """

    # Default guitar strum zone covers lower-middle / lower-right portion of camera frame.
    DEFAULT_STRUM_ZONE = Rect(ymin=0.50, xmin=0.20, ymax=1.00, xmax=0.85)

    def __init__(
        self,
        strum_zone: Optional[Rect] = None,
        velocity_threshold: float = 2.5,
        reversal_window: float = 0.35,
        reversal_count_trigger: int = 3,
    ):
        if not math.isfinite(velocity_threshold) or velocity_threshold <= 0:
            raise ValueError('velocity_threshold must be positive and finite')
        if not math.isfinite(reversal_window) or reversal_window <= 0:
            raise ValueError('reversal_window must be positive and finite')
        if not isinstance(reversal_count_trigger, int) or reversal_count_trigger < 2:
            raise ValueError('reversal_count_trigger must be an integer >= 2')

        self.strum_zone = strum_zone or self.DEFAULT_STRUM_ZONE
        self.velocity_threshold = velocity_threshold
        self.reversal_window = reversal_window
        self.reversal_count_trigger = reversal_count_trigger

        self.last_x: Optional[float] = None
        self.last_y: Optional[float] = None
        self.last_time: Optional[float] = None
        self.last_velocity_sign: int = 0
        self.reversal_times: list[float] = []
        self.strumming_detected: bool = False

    def reset(self):
        self.last_x = self.last_y = self.last_time = None
        self.last_velocity_sign = 0
        self.reversal_times.clear()
        self.strumming_detected = False

    def is_in_strum_zone(self, x: float, y: float) -> bool:
        if x is None or y is None or not math.isfinite(x) or not math.isfinite(y):
            return False
        return self.strum_zone.contains(x, y)

    def update(self, x: float, y: float, now: float) -> Tuple[bool, str]:
        """Check if hand movement represents guitar strumming or is in strum zone.

        Returns:
            (suppressed: bool, reason: str)
            reason is one of: 'expression_zone', 'strum_zone', 'strum_motion'.
        """
        if x is None or y is None or not all(math.isfinite(v) for v in (x, y, now)):
            self.reset()
            return False, 'no_hand'

        in_zone = self.is_in_strum_zone(x, y)

        # Clean old reversal history outside window.
        self.reversal_times = [t for t in self.reversal_times if now - t <= self.reversal_window]

        if self.last_time is not None and now > self.last_time:
            dt = now - self.last_time
            if dt > 0:
                # Vertical/horizontal velocity in normalized coordinates per second.
                dy = y - self.last_y
                vel_y = dy / dt

                # Detect strumming reversal (change of direction with significant velocity).
                if abs(vel_y) > 0.4:
                    current_sign = 1 if vel_y > 0 else -1
                    if self.last_velocity_sign != 0 and current_sign != self.last_velocity_sign:
                        self.reversal_times.append(now)
                    self.last_velocity_sign = current_sign

                speed = math.hypot(x - self.last_x, dy) / dt
                if speed > self.velocity_threshold:
                    self.reversal_times.append(now)

        self.last_x, self.last_y, self.last_time = x, y, now

        if len(self.reversal_times) >= self.reversal_count_trigger:
            self.strumming_detected = True
            return True, 'strum_motion'

        if in_zone:
            return True, 'strum_zone'

        self.strumming_detected = False
        return False, 'expression_zone'
