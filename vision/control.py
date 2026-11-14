"""Deterministic gesture mapping; times are monotonic seconds."""
import math
from dataclasses import dataclass


@dataclass
class Controller:
    low: float = 0.8
    high: float = 0.2
    rate: float = 20.0
    confidence: float = 0.6
    deadband: float = 0.015
    tau: float = 0.12
    control: str = 'filter'

    def __post_init__(self):
        if not all(math.isfinite(x) for x in (self.low, self.high, self.rate, self.confidence, self.deadband, self.tau)):
            raise ValueError('configuration must be finite')
        if not 0 <= self.high < self.low <= 1 or self.low - self.high < 0.05:
            raise ValueError('calibration needs separated high and low positions in [0,1]')
        if not 0 < self.rate <= 60 or not 0 <= self.confidence <= 1 or not 0 <= self.deadband < 1 or self.tau <= 0:
            raise ValueError('invalid rate, confidence, deadband or smoothing')
        if self.control not in ('filter', 'reverb'):
            raise ValueError('unsupported control')
        self.active = False
        self.armed = False
        self.value = None
        self.previous = None
        self.sent_at = -math.inf
        self.sent_value = None
        self.seq = 0

    def update(self, y, pinch, confidence, now, timestamp_ms):
        if y is None or pinch is None or not all(math.isfinite(v) for v in (y, pinch, confidence, now)) or not 0 <= confidence <= 1 or confidence < self.confidence:
            self.active = self.armed = False
            self.previous = None
            self.value = None
            return None
        if self.previous is not None and now <= self.previous:
            return None
        if pinch >= 0.45:
            self.active = False
            self.armed = True
            self.value = None
        elif self.armed and pinch <= 0.25:
            self.active = True
        dt = 0 if self.previous is None else now - self.previous
        self.previous = now
        if not self.active:
            return None
        target = min(1., max(0., (self.low - y) / (self.low - self.high)))
        self.value = target if self.value is None else self.value + (1 - math.exp(-dt / self.tau)) * (target - self.value)
        if now - self.sent_at < 1 / self.rate or (self.sent_value is not None and abs(self.value - self.sent_value) < self.deadband):
            return None
        event = dict(version=1, source='vision', seq=self.seq, timestamp_ms=timestamp_ms,
                     type='parameter', control=self.control, value=self.value, confidence=confidence)
        self.seq += 1
        self.sent_at, self.sent_value = now, self.value
        return event
