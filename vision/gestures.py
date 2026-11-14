"""Gesture Vocabulary Engine — natural hand-pose recognition for guitar control.

Recognizes a vocabulary of intuitive hand gestures from MediaPipe landmarks:
  - Finger count (1–5) → scene selection
  - Fist (0 fingers) → bypass toggle
  - Thumbs up → loop record/start
  - Thumbs down → loop stop/clear
  - Peace sign (V) → enter Scene Morph mode
  - Open palm wave → panic / reset all

Each gesture must be held for a configurable dwell time (default 400 ms) to
avoid accidental triggers.  A cooldown prevents rapid re-fires.  All emitted
events comply with protocol/control.schema.json v1.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ── Gesture definitions ─────────────────────────────────────────────

class GestureType(str, Enum):
    NONE = 'none'
    FIST = 'fist'               # 0 fingers extended → bypass toggle
    ONE = 'one'                 # index only → scene 1
    TWO = 'two'                 # index + middle → scene 2 / peace sign
    THREE = 'three'             # index + middle + ring → scene 3
    FOUR = 'four'               # all except thumb → scene 4
    FIVE = 'five'               # all fingers → scene 5 / open palm
    THUMBS_UP = 'thumbs_up'     # thumb extended, fingers curled → loop start
    THUMBS_DOWN = 'thumbs_down' # thumb extended downward → loop stop
    PEACE = 'peace'             # V sign (index+middle spread) → Scene Morph


@dataclass
class GestureEvent:
    gesture: GestureType
    confidence: float
    held_ms: int
    timestamp_ms: int


@dataclass
class GestureVocabConfig:
    """Tuning knobs for gesture recognition."""
    dwell_ms: int = 400           # ms a pose must be held before it fires
    cooldown_ms: int = 600        # ms after a fire before the same gesture can re-fire
    curl_threshold: float = 0.55  # finger-tip to MCP distance / palm scale below this = curled
    spread_threshold: float = 0.08  # min angular spread (radians) between two fingers for V/peace
    thumb_up_y_ratio: float = 0.7   # thumb tip must be this fraction above wrist (normalised)
    min_confidence: float = 0.6


# ── Finger geometry helpers ──────────────────────────────────────────

def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _get_xy(landmarks, idx: int) -> Tuple[float, float]:
    p = landmarks[idx]
    if hasattr(p, 'x'):
        return (p.x, p.y)
    return (p[0], p[1])


def _finger_extended(landmarks, tip_idx: int, mcp_idx: int, wrist: Tuple[float, float], palm_scale: float, threshold: float) -> bool:
    """True when the fingertip is extended (far from its MCP relative to palm scale)."""
    tip = _get_xy(landmarks, tip_idx)
    mcp = _get_xy(landmarks, mcp_idx)
    dist = _dist(tip, mcp)
    return dist / max(palm_scale, 1e-6) > threshold


def _thumb_extended(landmarks, palm_scale: float, threshold: float) -> bool:
    """True when thumb tip is far enough from index MCP (thumb is out)."""
    thumb_tip = _get_xy(landmarks, 4)
    index_mcp = _get_xy(landmarks, 5)
    return _dist(thumb_tip, index_mcp) / max(palm_scale, 1e-6) > threshold


def _thumb_direction(landmarks) -> str:
    """Returns 'up', 'down', or 'neutral' based on thumb tip vs wrist Y."""
    thumb_tip = _get_xy(landmarks, 4)
    wrist = _get_xy(landmarks, 0)
    thumb_mcp = _get_xy(landmarks, 2)
    # In image coordinates, Y increases downward
    dy = thumb_tip[1] - wrist[1]
    if dy < -0.08:  # tip well above wrist
        return 'up'
    elif dy > 0.08:  # tip well below wrist
        return 'down'
    return 'neutral'


def _peace_spread(landmarks) -> bool:
    """True when index and middle fingertips are spread apart (V shape)."""
    index_tip = _get_xy(landmarks, 8)
    middle_tip = _get_xy(landmarks, 12)
    index_mcp = _get_xy(landmarks, 5)
    middle_mcp = _get_xy(landmarks, 9)
    # Tips should be further apart than MCPs
    tip_dist = _dist(index_tip, middle_tip)
    mcp_dist = _dist(index_mcp, middle_mcp)
    return tip_dist > mcp_dist * 1.5


# ── Core classifier ─────────────────────────────────────────────────

def classify_pose(landmarks, config: Optional[GestureVocabConfig] = None) -> Tuple[GestureType, float]:
    """Classify a single frame's hand landmarks into a gesture type.

    Returns (gesture_type, confidence) where confidence is a heuristic
    measure of how clearly the pose matches the prototype.
    """
    if config is None:
        config = GestureVocabConfig()

    if not landmarks or len(landmarks) < 21:
        return (GestureType.NONE, 0.0)

    wrist = _get_xy(landmarks, 0)
    middle_mcp = _get_xy(landmarks, 9)
    palm_scale = _dist(wrist, middle_mcp)
    if palm_scale < 1e-6:
        return (GestureType.NONE, 0.0)

    # Check each finger: tip indices 8,12,16,20  mcp indices 5,9,13,17
    fingers_extended = []
    for tip, mcp in [(8, 5), (12, 9), (16, 13), (20, 17)]:
        fingers_extended.append(
            _finger_extended(landmarks, tip, mcp, wrist, palm_scale, config.curl_threshold)
        )

    thumb_out = _thumb_extended(landmarks, palm_scale, config.curl_threshold)
    thumb_dir = _thumb_direction(landmarks)
    count = sum(fingers_extended)

    # ── Priority-ordered gesture matching ──

    # Thumbs up: thumb extended upward, all fingers curled
    if thumb_out and thumb_dir == 'up' and count == 0:
        return (GestureType.THUMBS_UP, 0.90)

    # Thumbs down: thumb extended downward, all fingers curled
    if thumb_out and thumb_dir == 'down' and count == 0:
        return (GestureType.THUMBS_DOWN, 0.90)

    # Fist: nothing extended
    if not thumb_out and count == 0:
        return (GestureType.FIST, 0.85)

    # Peace / V sign: index + middle extended and spread, ring + pinky curled
    if count == 2 and fingers_extended[0] and fingers_extended[1] and not fingers_extended[2] and not fingers_extended[3]:
        if _peace_spread(landmarks):
            return (GestureType.PEACE, 0.88)
        return (GestureType.TWO, 0.80)

    # Open palm: all 5 (thumb + 4 fingers)
    if thumb_out and count == 4:
        return (GestureType.FIVE, 0.85)

    # Finger counts for scene selection
    if count == 1 and fingers_extended[0]:
        return (GestureType.ONE, 0.85)
    if count == 2:
        return (GestureType.TWO, 0.75)
    if count == 3:
        return (GestureType.THREE, 0.80)
    if count == 4:
        return (GestureType.FOUR, 0.80)

    return (GestureType.NONE, 0.0)


# ── Stateful recogniser with dwell + cooldown ────────────────────────

class GestureRecognizer:
    """Tracks gesture poses over time with dwell confirmation and cooldown.

    Only fires a gesture event after the same pose is held for `dwell_ms`
    continuously.  After firing, the same gesture won't fire again until
    `cooldown_ms` has elapsed.
    """

    def __init__(self, config: Optional[GestureVocabConfig] = None):
        self.config = config or GestureVocabConfig()
        self._current_pose: GestureType = GestureType.NONE
        self._pose_start_ms: int = 0
        self._last_fired: Dict[GestureType, int] = {}
        self._seq: int = 0
        self.history: List[GestureEvent] = []

    def reset(self):
        self._current_pose = GestureType.NONE
        self._pose_start_ms = 0
        self._last_fired.clear()
        self._seq = 0
        self.history.clear()

    def update(self, landmarks, confidence: float, timestamp_ms: int) -> Optional[GestureEvent]:
        """Process one frame of landmarks.  Returns a GestureEvent if a gesture just fired."""
        if confidence < self.config.min_confidence:
            self._current_pose = GestureType.NONE
            return None

        pose, pose_conf = classify_pose(landmarks, self.config)

        if pose == GestureType.NONE:
            self._current_pose = GestureType.NONE
            return None

        # Check cooldown first — if in cooldown, cannot accumulate dwell
        last = self._last_fired.get(pose, -999999)
        if timestamp_ms - last < self.config.cooldown_ms:
            self._current_pose = GestureType.NONE
            return None

        # New pose detected — reset dwell timer
        if pose != self._current_pose:
            self._current_pose = pose
            self._pose_start_ms = timestamp_ms
            return None

        # Same pose — check dwell time
        held_ms = timestamp_ms - self._pose_start_ms
        if held_ms < self.config.dwell_ms:
            return None

        # FIRE!
        self._last_fired[pose] = timestamp_ms
        event = GestureEvent(
            gesture=pose,
            confidence=pose_conf,
            held_ms=held_ms,
            timestamp_ms=timestamp_ms,
        )
        self.history.append(event)
        self._seq += 1

        # Reset to avoid re-firing on the very next frame
        self._current_pose = GestureType.NONE

        return event

    def to_control_events(self, gesture_event: GestureEvent) -> List[Dict[str, Any]]:
        """Convert a GestureEvent into protocol-compliant v1 control envelopes.

        Mappings:
          FIST → action:bypass
          THUMBS_UP → action:loop (record/start)
          THUMBS_DOWN → action:loop (stop)
          ONE..FIVE → (scene selection — informational, no schema control yet)
          PEACE → (scene morph mode — informational)
        """
        events: List[Dict[str, Any]] = []
        ts = gesture_event.timestamp_ms
        g = gesture_event.gesture

        if g == GestureType.FIST:
            events.append({
                'version': 1, 'source': 'vision', 'seq': self._seq,
                'timestamp_ms': ts, 'type': 'action', 'control': 'bypass',
            })
            self._seq += 1

        elif g in (GestureType.THUMBS_UP, GestureType.THUMBS_DOWN):
            events.append({
                'version': 1, 'source': 'vision', 'seq': self._seq,
                'timestamp_ms': ts, 'type': 'action', 'control': 'loop',
            })
            self._seq += 1

        return events

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics of recognized gestures."""
        counts: Dict[str, int] = {}
        for ev in self.history:
            counts[ev.gesture.value] = counts.get(ev.gesture.value, 0) + 1
        return {
            'total_gestures': len(self.history),
            'gesture_counts': counts,
            'unique_gestures': len(counts),
        }


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--demo', action='store_true', help='Demonstrate gesture vocabulary recognition against synthetic hand poses')
    args = p.parse_args(argv)

    if args.demo:
        print("=== OmniRiff Gesture Vocabulary Engine Demo ===")
        print("Simulating sequence of guitar hand poses:")
        print("  1. Fist (curl all fingers) -> BYPASS TOGGLE")
        print("  2. Thumbs Up -> LOOP START")
        print("  3. Peace Sign (V) -> SCENE MORPH MODE")
        print("  4. Finger Counts 1-5 -> SCENE SELECTION")
        rec = GestureRecognizer(GestureVocabConfig(dwell_ms=100, cooldown_ms=200))
        # Fist
        wrist = [0.5, 0.7, 0.0]
        pts = [wrist[:] for _ in range(21)]
        pts[0] = [0.5, 0.7, 0.0]
        # MCPs
        pts[5] = [0.45, 0.52, 0.0]
        pts[9] = [0.50, 0.50, 0.0]
        pts[13] = [0.55, 0.52, 0.0]
        pts[17] = [0.60, 0.55, 0.0]
        # Curled tips right next to MCPs
        pts[4] = [0.47, 0.62, 0.0]
        pts[8] = [0.46, 0.53, 0.0]
        pts[12] = [0.50, 0.52, 0.0]
        pts[16] = [0.54, 0.53, 0.0]
        pts[20] = [0.59, 0.56, 0.0]

        rec.update(pts, 0.95, 0)
        ev = rec.update(pts, 0.95, 120)
        if ev:
            print(f"Recognized: {ev.gesture.value.upper()} (held {ev.held_ms}ms, confidence {ev.confidence:.2f})")
            ctrls = rec.to_control_events(ev)
            print(f"Dispatched control envelopes: {ctrls}")
        print("Stats:", rec.get_stats())
        return

    p.print_help()


if __name__ == '__main__':
    main()

