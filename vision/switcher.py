"""Live gesture-based effect switcher using thumb-to-pinky contact."""
import math
from typing import List, Optional


class EffectSwitcher:
    """Detects deliberate thumb-to-pinky contact to cycle active effect.

    Requires holding thumb and pinky tips together (pinch <= touch_threshold)
    for hold_seconds to switch. Once switched, requires releasing the contact
    (pinch >= release_threshold) before another switch can occur.
    """

    def __init__(
        self,
        controls: Optional[List[str]] = None,
        touch_threshold: float = 0.30,
        release_threshold: float = 0.45,
        hold_seconds: float = 0.20,
        min_confidence: float = 0.60,
    ):
        self.controls = list(controls or ['filter', 'reverb'])
        if len(self.controls) < 2:
            raise ValueError('EffectSwitcher requires at least 2 controls to cycle between')
        self.touch_threshold = touch_threshold
        self.release_threshold = release_threshold
        self.hold_seconds = hold_seconds
        self.min_confidence = min_confidence

        self.index = 0
        self.touch_start: Optional[float] = None
        self.latched = False

    @property
    def current_control(self) -> str:
        return self.controls[self.index]

    def set_control(self, control: str) -> None:
        if control in self.controls:
            self.index = self.controls.index(control)

    def update(
        self,
        pinky_pinch: Optional[float],
        confidence: float,
        now: float,
        controller=None,
    ) -> bool:
        """Update switcher state with current frame's pinky pinch distance.

        Returns True if a control switch occurred on this frame.
        """
        if (
            pinky_pinch is None
            or not math.isfinite(pinky_pinch)
            or not math.isfinite(now)
            or confidence < self.min_confidence
        ):
            self.touch_start = None
            return False

        # If latched, wait for release
        if self.latched:
            if pinky_pinch >= self.release_threshold:
                self.latched = False
                self.touch_start = None
            return False

        # Check for touch contact
        if pinky_pinch <= self.touch_threshold:
            if self.touch_start is None:
                self.touch_start = now
            elif (now - self.touch_start) >= (self.hold_seconds - 1e-4):
                # Trigger switch!
                self.index = (self.index + 1) % len(self.controls)
                self.latched = True
                self.touch_start = None

                if controller is not None:
                    controller.control = self.current_control
                    controller.rearm()

                return True
        else:
            self.touch_start = None

        return False
