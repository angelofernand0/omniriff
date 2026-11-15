"""Live gesture-based effect switcher using thumb-to-pinky contact."""
import math
from typing import Dict, List, Optional


class EffectSwitcher:
    """Detects deliberate thumb-to-pinky contact to cycle active effect.

    Requires holding thumb and pinky tips together (pinch <= touch_threshold)
    for hold_seconds to switch. Once switched, requires releasing the contact
    (pinch >= release_threshold) before another switch can occur.
    Preserves independent per-effect pickup values so relative control
    picks up right where each effect left off without jumps.
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
        if not math.isfinite(hold_seconds) or hold_seconds <= 0:
            raise ValueError('hold_seconds must be a positive finite number')
        if not math.isfinite(min_confidence) or not 0 <= min_confidence <= 1:
            raise ValueError('min_confidence must be in [0, 1]')
        if (
            not math.isfinite(touch_threshold)
            or not math.isfinite(release_threshold)
            or not 0 < touch_threshold < release_threshold <= 1
        ):
            raise ValueError('touch and release thresholds must be finite with 0 < touch < release <= 1')

        self.touch_threshold = touch_threshold
        self.release_threshold = release_threshold
        self.hold_seconds = hold_seconds
        self.min_confidence = min_confidence

        self.index = 0
        self.touch_start: Optional[float] = None
        self.latched = False
        # Store per-control last sent values to maintain independent relative pickup
        self.saved_sent_values: Dict[str, Optional[float]] = {c: None for c in self.controls}

    @property
    def current_control(self) -> str:
        return self.controls[self.index]

    def set_control(self, control: str) -> None:
        if control in self.controls:
            self.index = self.controls.index(control)

    def reset_dwell(self) -> None:
        """Reset pending touch dwell timer."""
        self.touch_start = None

    def update(
        self,
        pinky_pinch: Optional[float],
        confidence: float,
        now: float,
        controller=None,
        suppressed: bool = False,
    ) -> bool:
        """Update switcher state with current frame's pinky pinch distance.

        Resets touch dwell on missing, stale, low-confidence, or suppressed frames.
        Returns True if a control switch occurred on this frame.
        """
        # Validate inputs and check for suppression
        if (
            suppressed
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
            or confidence < self.min_confidence
            or pinky_pinch is None
            or not math.isfinite(pinky_pinch)
            or not math.isfinite(now)
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
                old_control = self.current_control
                self.index = (self.index + 1) % len(self.controls)
                new_control = self.current_control
                self.latched = True
                self.touch_start = None

                if controller is not None:
                    # Save old effect's sent_value before rearming
                    self.saved_sent_values[old_control] = controller.sent_value
                    # Switch controller target
                    controller.control = new_control
                    controller.rearm()
                    # Restore new effect's independent pickup value
                    controller.sent_value = self.saved_sent_values.get(new_control)

                return True
        else:
            self.touch_start = None

        return False
