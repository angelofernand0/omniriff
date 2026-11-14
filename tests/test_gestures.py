"""Tests for Gesture Vocabulary Engine (vision/gestures.py).

Validates pose classification, dwell/cooldown state machine, and
strict compliance with protocol/control.schema.json v1.
"""
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from vision.gestures import (
    GestureEvent,
    GestureRecognizer,
    GestureType,
    GestureVocabConfig,
    classify_pose,
)


def _make_mock_landmarks(
    fingers_extended=(False, False, False, False),
    thumb_out=False,
    thumb_direction='neutral',
    spread=False,
):
    """Build a 21-landmark list matching MediaPipe HandLandmarker format.

    Wrist at (0.5, 0.7).
    Palm scale ~ 0.2 (wrist to middle MCP at (0.5, 0.5)).
    """
    pts = [[0.5, 0.7, 0.0] for _ in range(21)]
    # Wrist (0)
    pts[0] = [0.5, 0.7, 0.0]

    # Thumb: MCP(2), IP(3), Tip(4)
    pts[2] = [0.45, 0.65, 0.0]
    pts[3] = [0.42, 0.60, 0.0]
    if thumb_out:
        if thumb_direction == 'up':
            pts[4] = [0.40, 0.40, 0.0]  # well above wrist (0.40 < 0.7 - 0.08)
        elif thumb_direction == 'down':
            pts[4] = [0.40, 0.85, 0.0]  # well below wrist (0.85 > 0.7 + 0.08)
        else:
            pts[4] = [0.30, 0.60, 0.0]
    else:
        # Tucked thumb
        pts[4] = [0.47, 0.62, 0.0]

    # Index: MCP(5), PIP(6), DIP(7), Tip(8)
    pts[5] = [0.45, 0.52, 0.0]
    if fingers_extended[0]:
        pts[8] = [0.40 if spread else 0.45, 0.25, 0.0]  # extended high
    else:
        pts[8] = [0.46, 0.54, 0.0]  # curled close to MCP

    # Middle: MCP(9), PIP(10), DIP(11), Tip(12)
    pts[9] = [0.50, 0.50, 0.0]
    if fingers_extended[1]:
        pts[12] = [0.55 if spread else 0.50, 0.25, 0.0]  # extended high
    else:
        pts[12] = [0.50, 0.53, 0.0]  # curled close to MCP

    # Ring: MCP(13), PIP(14), DIP(15), Tip(16)
    pts[13] = [0.55, 0.52, 0.0]
    if fingers_extended[2]:
        pts[16] = [0.55, 0.25, 0.0]
    else:
        pts[16] = [0.54, 0.54, 0.0]

    # Pinky: MCP(17), PIP(18), DIP(19), Tip(20)
    pts[17] = [0.60, 0.55, 0.0]
    if fingers_extended[3]:
        pts[20] = [0.60, 0.28, 0.0]
    else:
        pts[20] = [0.59, 0.57, 0.0]

    return pts


class GestureVocabTests(unittest.TestCase):
    def setUp(self):
        schema_path = Path(__file__).resolve().parents[1] / 'protocol/control.schema.json'
        self.schema = json.loads(schema_path.read_text())
        self.validator = Draft202012Validator(self.schema)

    def test_classify_empty_or_short_landmarks(self):
        self.assertEqual(classify_pose([])[0], GestureType.NONE)
        self.assertEqual(classify_pose([[0, 0]] * 10)[0], GestureType.NONE)

    def test_classify_fist(self):
        # All fingers curled, thumb tucked
        pts = _make_mock_landmarks(fingers_extended=(False, False, False, False), thumb_out=False)
        g, conf = classify_pose(pts)
        self.assertEqual(g, GestureType.FIST)
        self.assertGreater(conf, 0.7)

    def test_classify_thumbs_up_and_down(self):
        pts_up = _make_mock_landmarks(fingers_extended=(False, False, False, False), thumb_out=True, thumb_direction='up')
        g_up, conf_up = classify_pose(pts_up)
        self.assertEqual(g_up, GestureType.THUMBS_UP)
        self.assertGreater(conf_up, 0.8)

        pts_down = _make_mock_landmarks(fingers_extended=(False, False, False, False), thumb_out=True, thumb_direction='down')
        g_down, conf_down = classify_pose(pts_down)
        self.assertEqual(g_down, GestureType.THUMBS_DOWN)
        self.assertGreater(conf_down, 0.8)

    def test_classify_finger_counts(self):
        # 1 finger: index
        pts1 = _make_mock_landmarks(fingers_extended=(True, False, False, False), thumb_out=False)
        self.assertEqual(classify_pose(pts1)[0], GestureType.ONE)

        # 2 fingers: index + middle (not spread)
        pts2 = _make_mock_landmarks(fingers_extended=(True, True, False, False), thumb_out=False, spread=False)
        self.assertEqual(classify_pose(pts2)[0], GestureType.TWO)

        # 3 fingers
        pts3 = _make_mock_landmarks(fingers_extended=(True, True, True, False), thumb_out=False)
        self.assertEqual(classify_pose(pts3)[0], GestureType.THREE)

        # 4 fingers
        pts4 = _make_mock_landmarks(fingers_extended=(True, True, True, True), thumb_out=False)
        self.assertEqual(classify_pose(pts4)[0], GestureType.FOUR)

        # 5 fingers (open palm)
        pts5 = _make_mock_landmarks(fingers_extended=(True, True, True, True), thumb_out=True)
        self.assertEqual(classify_pose(pts5)[0], GestureType.FIVE)

    def test_classify_peace_sign(self):
        pts_peace = _make_mock_landmarks(fingers_extended=(True, True, False, False), thumb_out=False, spread=True)
        g, conf = classify_pose(pts_peace)
        self.assertEqual(g, GestureType.PEACE)
        self.assertGreater(conf, 0.8)

    def test_recognizer_dwell_time_and_cooldown(self):
        rec = GestureRecognizer(GestureVocabConfig(dwell_ms=300, cooldown_ms=500))
        pts_fist = _make_mock_landmarks(fingers_extended=(False, False, False, False), thumb_out=False)

        # Frame 1: at t=0ms -> not fired yet
        ev = rec.update(pts_fist, confidence=0.9, timestamp_ms=0)
        self.assertIsNone(ev)

        # Frame 2: at t=200ms -> dwell not met (200 < 300)
        ev = rec.update(pts_fist, confidence=0.9, timestamp_ms=200)
        self.assertIsNone(ev)

        # Frame 3: at t=350ms -> dwell met (350 >= 300) -> FIRES!
        ev = rec.update(pts_fist, confidence=0.9, timestamp_ms=350)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.gesture, GestureType.FIST)

        # Frame 4: at t=400ms -> in cooldown (400 - 350 < 500) -> None
        ev = rec.update(pts_fist, confidence=0.9, timestamp_ms=400)
        self.assertIsNone(ev)

        # Frame 5: after cooldown at t=900ms -> dwell restarts
        ev = rec.update(pts_fist, confidence=0.9, timestamp_ms=900)
        self.assertIsNone(ev)
        # At t=1250ms -> fires again
        ev = rec.update(pts_fist, confidence=0.9, timestamp_ms=1250)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.gesture, GestureType.FIST)

    def test_recognizer_confidence_gate(self):
        rec = GestureRecognizer(GestureVocabConfig(dwell_ms=200, min_confidence=0.7))
        pts_fist = _make_mock_landmarks(fingers_extended=(False, False, False, False), thumb_out=False)

        # Low confidence drops gesture
        self.assertIsNone(rec.update(pts_fist, confidence=0.5, timestamp_ms=100))
        self.assertIsNone(rec.update(pts_fist, confidence=0.5, timestamp_ms=350))

    def test_recognizer_pose_switching_resets_dwell(self):
        rec = GestureRecognizer(GestureVocabConfig(dwell_ms=300))
        pts_fist = _make_mock_landmarks(fingers_extended=(False, False, False, False), thumb_out=False)
        pts_one = _make_mock_landmarks(fingers_extended=(True, False, False, False), thumb_out=False)

        # Fist for 200ms
        rec.update(pts_fist, confidence=0.9, timestamp_ms=0)
        rec.update(pts_fist, confidence=0.9, timestamp_ms=200)

        # Switch to ONE at 250ms
        rec.update(pts_one, confidence=0.9, timestamp_ms=250)

        # At 350ms, neither has dwelled for 300ms
        self.assertIsNone(rec.update(pts_one, confidence=0.9, timestamp_ms=350))

        # At 560ms (250 + 310), ONE fires
        ev = rec.update(pts_one, confidence=0.9, timestamp_ms=560)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.gesture, GestureType.ONE)

    def test_to_control_events_schema_compliance(self):
        rec = GestureRecognizer()

        # FIST -> bypass action
        fist_ev = GestureEvent(gesture=GestureType.FIST, confidence=0.85, held_ms=450, timestamp_ms=1000)
        ctrl_events = rec.to_control_events(fist_ev)
        self.assertEqual(len(ctrl_events), 1)
        self.assertEqual(ctrl_events[0]['control'], 'bypass')
        self.assertEqual(ctrl_events[0]['type'], 'action')
        self.validator.validate(ctrl_events[0])

        # THUMBS_UP -> loop action
        thumb_ev = GestureEvent(gesture=GestureType.THUMBS_UP, confidence=0.9, held_ms=500, timestamp_ms=2000)
        ctrl_events = rec.to_control_events(thumb_ev)
        self.assertEqual(len(ctrl_events), 1)
        self.assertEqual(ctrl_events[0]['control'], 'loop')
        self.assertEqual(ctrl_events[0]['type'], 'action')
        self.validator.validate(ctrl_events[0])

    def test_stats_and_reset(self):
        rec = GestureRecognizer(GestureVocabConfig(dwell_ms=100, cooldown_ms=100))
        pts_fist = _make_mock_landmarks(fingers_extended=(False, False, False, False), thumb_out=False)

        rec.update(pts_fist, 0.9, 0)
        rec.update(pts_fist, 0.9, 150)

        stats = rec.get_stats()
        self.assertEqual(stats['total_gestures'], 1)
        self.assertEqual(stats['gesture_counts'].get('fist'), 1)

        rec.reset()
        self.assertEqual(rec.get_stats()['total_gestures'], 0)


if __name__ == '__main__':
    unittest.main()
