"""Off-callback onset analysis of the audio owner's continuous input snapshot."""
from __future__ import annotations

import asyncio
import logging
import statistics
import time

LOG = logging.getLogger('omniriff.live')
WINDOW_S = 2.0
STALE_S = .5
SETTLE_S = .05
MIN_GAP_S = .07  # Ears' minimum inter-strum distance, also across windows.


class LiveAnalysis:
    def __init__(self, audio, *, clock=None, monotonic=None, detector=None):
        self.audio = audio
        self.clock = clock or (lambda: int(time.time()*1000))
        self.monotonic = monotonic or time.monotonic
        self.detector = detector
        self.enabled = True
        self.state = None
        self.end = self.rate = self.advanced_at = None
        self.committed = -1
        self.onsets = []
        self.last_onset = self.last_ms = None

    def stop(self):
        self.enabled = False

    def snapshot(self):
        if (not self.enabled or self.state is None or self.advanced_at is None
                or self.monotonic()-self.advanced_at > STALE_S):
            return None
        return dict(self.state)

    def baseline(self, end, rate, now):
        self.end, self.rate, self.advanced_at = end, rate, now
        self.committed = end
        self.onsets = []
        self.last_onset = self.last_ms = None
        self.state = None

    def update(self):
        """Worker-thread only; no audio samples are logged or retained here."""
        if not self.enabled: return
        import numpy as np
        window, end, rate = self.audio.snapshot_input(WINDOW_S)
        now, wall_ms = self.monotonic(), self.clock()
        if (rate <= 0 or end < 0 or window.ndim != 1 or len(window) < int(WINDOW_S*rate)
                or not np.isfinite(window).all()):
            raise ValueError('input snapshot is invalid or too short')
        if (self.end is None or rate != self.rate or end < self.end
                or (self.advanced_at is not None and now-self.advanced_at > STALE_S)):
            # Don't present old buffered sound as a fresh onset after startup,
            # pause or reset. Wait for a new advancing input snapshot.
            self.baseline(end,rate,now)
            return
        if end == self.end: return
        if self.detector is None:
            from tools.ears import detect_onsets
            detector = detect_onsets
        else:
            detector = self.detector
        final = end-int(SETTLE_S*rate)
        accepted = []
        last = self.last_onset
        for milliseconds in detector(window,rate):
            frame = end-len(window)+round(float(milliseconds)*rate/1000)
            if not self.committed < frame <= final or frame < 0: continue
            if last is not None and frame-last < MIN_GAP_S*rate: continue
            accepted.append(frame)
            last = frame
        if not self.enabled: return  # Shutdown may have happened during analysis.
        self.end, self.advanced_at = end, now
        self.committed = max(self.committed,final)
        self.onsets = [frame for frame in self.onsets+accepted if end-frame <= WINDOW_S*rate]
        if accepted:
            self.last_onset = accepted[-1]
            # Host-receipt time aligned back to the detected sample; not an
            # independently measured ADC timestamp or latency measurement.
            self.last_ms = max(0,round(wall_ms-1000*(end-self.last_onset)/rate))
        steady = None
        if len(self.onsets)>=3:
            intervals = [b-a for a,b in zip(self.onsets,self.onsets[1:])]
            mean = statistics.fmean(intervals)
            steady = (mean > 0 and statistics.pstdev(intervals)/mean <= .2
                      and end-self.onsets[-1] <= 1.6*statistics.median(intervals))
        count = sum(0 <= end-frame < rate for frame in self.onsets)
        self.state = dict(strums_last_s=count,last_strum_ms=self.last_ms if count else None,
                          steady=steady if count else None)

    async def run(self):
        self.enabled = True
        last_error = None
        try:
            while True:
                start = self.monotonic()
                try:
                    await asyncio.to_thread(self.update)
                    last_error = None
                except Exception as exc:
                    self.state = None
                    message = f'{type(exc).__name__}: {exc}'[:240]
                    if message != last_error:
                        LOG.warning('live analysis unavailable (audio independent): %s',message)
                        last_error = message
                await asyncio.sleep(max(0,.1-(self.monotonic()-start)))
        finally:
            self.stop()
