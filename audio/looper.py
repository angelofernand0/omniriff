"""Single-track looper: idle -> recording -> playing -> idle (cleared)."""
from __future__ import annotations

import numpy as np

IDLE = "idle"
RECORDING = "recording"
PLAYING = "playing"


class Looper:
    def __init__(self, max_frames: int, fade_frames: int):
        self.buf = np.zeros(max_frames, dtype=np.float32)
        self.max_frames = max_frames
        self.fade_frames = fade_frames
        self.length = 0
        self.pos = 0
        self.state = IDLE

    def toggle(self) -> None:
        if self.state == IDLE:
            self.length = 0
            self.pos = 0
            self.state = RECORDING
        elif self.state == RECORDING:
            self._finish_recording()
        else:
            self.length = 0
            self.pos = 0
            self.state = IDLE

    def _finish_recording(self) -> None:
        if self.length == 0:
            self.state = IDLE
            return
        fade = min(self.fade_frames, self.length // 4)
        if fade > 0:
            # Short fades at both ends so the loop seam does not click.
            ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            self.buf[:fade] *= ramp
            self.buf[self.length - fade:self.length] *= ramp[::-1]
        self.pos = 0
        self.state = PLAYING

    def process(self, dry: np.ndarray, out: np.ndarray) -> None:
        """Record from `dry` and/or write loop playback into `out` (same length)."""
        n = len(dry)
        if self.state == RECORDING:
            k = min(n, self.max_frames - self.length)
            self.buf[self.length:self.length + k] = dry[:k]
            self.length += k
            out[:n] = 0.0
            if self.length >= self.max_frames:
                self._finish_recording()
        elif self.state == PLAYING:
            i = 0
            while i < n:
                k = min(n - i, self.length - self.pos)
                out[i:i + k] = self.buf[self.pos:self.pos + k]
                i += k
                self.pos += k
                if self.pos >= self.length:
                    self.pos = 0
        else:
            out[:n] = 0.0
