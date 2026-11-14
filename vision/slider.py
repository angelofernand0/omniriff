"""Relative clutch that picks up the actual rig target at every engagement."""
import math
from .control import Controller


class FilterSlider:
    def __init__(self, read_target, *, rate=20):
        self.read_target = read_target
        self.controller = Controller(relative=True, control='filter', rate=rate)
        self.error = None

    def update(self, y, pinch, confidence, now, timestamp_ms):
        c = self.controller
        valid = (y is not None and pinch is not None and
                 all(math.isfinite(v) for v in (y, pinch, confidence, now)) and
                 c.confidence <= confidence <= 1)
        if valid and c.armed and not c.active and pinch <= .25:
            try:
                value = self.read_target()
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError('filter target must be a finite value in [0,1]')
            except Exception as exc:
                self.error = f'Pickup unavailable: {type(exc).__name__}'
                c.rearm()
                return None
            # Suppress a redundant first send. The rig already holds this value.
            c.sent_value = c.value = value
            self.error = None
        return c.update(y, pinch, confidence, now, timestamp_ms)
