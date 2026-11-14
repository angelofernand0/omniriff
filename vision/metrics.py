"""Bounded timing evidence for capture processing, not audio round-trip latency."""
from collections import deque
import math
import threading


class FrameMetrics:
    def __init__(self, capacity=2048):
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError('capacity must be positive')
        self.samples = deque(maxlen=capacity)
        self.lock = threading.Lock()
        self.first = self.last = None
        self.frames = self.events = 0
        self.total_ms = 0.
        self.hand_frames = self.presence_frames = 0

    def record(self, started, finished, events, *, hand_present=None):
        if not all(math.isfinite(v) for v in (started, finished)) or finished < started or type(events) is not int or events < 0:
            raise ValueError('invalid frame measurement')
        if hand_present is not None and type(hand_present) is not bool:
            raise ValueError('hand presence must be boolean or unknown')
        with self.lock:
            if self.last is not None and started < self.last:
                raise ValueError('frames must be sequential')
            if self.first is None:
                self.first = started
            self.last = finished
            elapsed = (finished-started)*1000
            self.frames += 1
            self.events += events
            self.total_ms += elapsed
            if hand_present is not None:
                self.presence_frames += 1
                self.hand_frames += int(hand_present)
            self.samples.append(elapsed)

    def snapshot(self):
        with self.lock:
            duration = self.last-self.first if self.first is not None else 0.
            values = sorted(self.samples)
            percentile = lambda q: values[min(len(values)-1, math.ceil(len(values)*q)-1)] if values else None
            return dict(frames=self.frames, events=self.events, observed_seconds=duration,
                        hand_present_frames=self.hand_frames, hand_presence_measured_frames=self.presence_frames,
                        processed_fps=self.frames/duration if duration else None,
                        emitted_events_hz=self.events/duration if duration else None,
                        processing_mean_ms=self.total_ms/self.frames if self.frames else None,
                        processing_p50_ms=percentile(.5), processing_p95_ms=percentile(.95),
                        percentile_window_frames=len(values),
                        measurement='frame available to final control send; excludes camera exposure, network delivery and audio latency')
