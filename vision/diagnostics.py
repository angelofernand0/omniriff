"""Cheap camera framing cues; these are not detector-accuracy measurements."""
from collections import deque
import math


class CameraDiagnostics:
    def __init__(self, window=31):
        if type(window) is not int or window < 2:
            raise ValueError('window must contain at least two frames')
        self.times = deque(maxlen=window)
        self.brightness = None
        self.hand_frames = self.absent_frames = self.dropouts = 0
        self.longest_absent_frames = self.absent_run = 0
        self.was_present = False

    def observe(self, frame, now, present):
        if not math.isfinite(now) or self.times and now <= self.times[-1]:
            raise ValueError('camera frame times must increase')
        if type(present) is not bool:
            raise ValueError('hand presence must be boolean')
        self.times.append(now)
        # A sparse whole-scene pixel average is a lighting *cue*, not a claim
        # that the hand itself is illuminated or detectable.
        sample = float(frame[::16, ::16].mean())
        self.brightness = sample if self.brightness is None else .8 * self.brightness + .2 * sample
        if present:
            self.hand_frames += 1
            self.absent_run = 0
        else:
            self.absent_frames += 1
            self.absent_run += 1
            self.longest_absent_frames = max(self.longest_absent_frames, self.absent_run)
            if self.was_present:
                self.dropouts += 1
        self.was_present = present

    def snapshot(self):
        duration = self.times[-1] - self.times[0] if len(self.times) > 1 else 0
        return dict(camera_fps=(len(self.times) - 1) / duration if duration > 0 else None,
                    scene_brightness_0_255=self.brightness,
                    hand_present_frames=self.hand_frames,
                    hand_absent_frames=self.absent_frames,
                    presence_dropouts=self.dropouts,
                    longest_absent_frames=self.longest_absent_frames)
