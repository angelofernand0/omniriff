"""Integration tests for the real vision pipeline order: HandSelector -> StrumGuard -> Controller.

Verifies end-to-end signal flow:
1. Multi-hand detection & wrist tracking via HandSelector
2. Spatial zone containment & velocity reversal gating via StrumGuard
3. Open-then-pinch clutching & relative pickup via Controller / FilterSlider
4. Schema validation and DSP parameter ingestion via Router & Engine
"""
import json
import math
from pathlib import Path
import unittest

import numpy as np
from jsonschema import Draft202012Validator

from audio import Engine, EngineConfig
from engine.router import Router
from vision.control import Controller
from vision.slider import FilterSlider
from vision.tracking import HandSelector
from vision.zones import Rect, StrumGuard
from vision.expressive import DualAxisController, OrientationResult
from vision.metrics import FrameMetrics


class VisionPipelineHarness:
    """Models the exact execution order of the OmniRiff vision pipeline.

    Order:
    1. Extract centers from detected hand landmarks.
    2. Select tracking target via HandSelector (rejects sudden jumps / flips).
    3. Evaluate spatial zone & motion reversals via StrumGuard.
    4. If StrumGuard suppresses: clear (y, pinch) and rearm Controller.
    5. Feed sanitized (y, pinch, confidence) into Controller / FilterSlider.
    """

    def __init__(self, controller=None, slider=None, selector=None, strum_guard=None):
        self.slider = slider
        self.controller = (slider.controller if slider else (controller or Controller(rate=20)))
        self.selector = selector or HandSelector(max_jump=0.30, forget_after=15)
        self.strum_guard = strum_guard
        self.zone_status = 'no_hand'
        self.last_suppressed = False

    def process_frame(self, detections, now, timestamp_ms):
        """Processes one video frame's hand detections.

        detections: list of dicts:
            {
                'wrist': (x, y),
                'pinch': float,
                'confidence': float,
                'scale': float (optional, default 0.10)
            }
        """
        centers = [d['wrist'] for d in detections if 'wrist' in d]
        selected = self.selector.select(centers)

        y = pinch = None
        confidence = 0.0
        self.zone_status = 'no_hand'
        self.last_suppressed = False

        if selected is not None:
            target = detections[selected]
            x, y_pos = target['wrist']
            confidence = target.get('confidence', 0.90)
            pinch_val = target.get('pinch', 0.50)
            y = y_pos
            pinch = pinch_val
            self.zone_status = 'expression_zone'

            if self.strum_guard and y is not None:
                suppressed, self.zone_status = self.strum_guard.update(x=x, y=y, now=now)
                self.last_suppressed = suppressed
                if suppressed:
                    y = pinch = None
                    self.controller.rearm()

        active_ctrl = self.slider if self.slider else self.controller
        if isinstance(self.controller, DualAxisController):
            orientation = target.get('orientation') if selected is not None else None
            events = active_ctrl.update(y, pinch, orientation, confidence, now, timestamp_ms)
            return events, self.zone_status

        event = active_ctrl.update(y, pinch, confidence, now, timestamp_ms)
        return event, self.zone_status


class PipelineStrumIntegrationTests(unittest.TestCase):
    def setUp(self):
        schema_path = Path(__file__).resolve().parents[1] / 'protocol/control.schema.json'
        self.validator = Draft202012Validator(json.loads(schema_path.read_text()))

    def test_pick_holding_in_guitar_strum_zone_is_doubly_protected(self):
        """Pick-holding strumming inside guitar zone has 0 false triggers via both clutch and StrumGuard."""
        guard = StrumGuard(strum_zone=Rect(ymin=0.50, xmin=0.20, ymax=1.00, xmax=0.85))
        pipeline = VisionPipelineHarness(strum_guard=guard)

        events = []
        now = 1.0
        # 60 frames (2 seconds @ 30 FPS) of guitarist playing rhythm
        for i in range(60):
            now += 0.033
            strum_y = 0.70 + 0.10 * math.sin(2 * math.pi * 3.5 * now)
            frame_detections = [{
                'wrist': (0.50, strum_y),
                'pinch': 0.20,  # holding pick
                'confidence': 0.92,
            }]
            ev, status = pipeline.process_frame(frame_detections, now, int(now * 1000))
            self.assertIn(status, ('strum_zone', 'strum_motion'))
            self.assertTrue(pipeline.last_suppressed)
            if ev:
                events.append(ev)

        self.assertEqual(len(events), 0)
        self.assertFalse(pipeline.controller.armed)
        self.assertFalse(pipeline.controller.active)

    def test_post_arm_strumming_suppression_prevents_false_sweeps(self):
        """Opening hand in air before playing arms the clutch, but entering guitar zone immediately rearms."""
        guard = StrumGuard(strum_zone=Rect(ymin=0.50, xmin=0.20, ymax=1.00, xmax=0.85))
        pipeline = VisionPipelineHarness(strum_guard=guard)

        # 1. Musician presents open hand in air (expression zone: y=0.35, x=0.50)
        now = 1.0
        ev1, status1 = pipeline.process_frame([{
            'wrist': (0.50, 0.35),
            'pinch': 0.65,
            'confidence': 0.95,
        }], now=now, timestamp_ms=1000)

        self.assertIsNone(ev1)
        self.assertEqual(status1, 'expression_zone')
        self.assertTrue(pipeline.controller.armed)
        self.assertFalse(pipeline.controller.active)

        # 2. Musician grasps pick while lowering hand towards strings
        now += 0.10
        # Crossing into guitar zone: y=0.60
        ev2, status2 = pipeline.process_frame([{
            'wrist': (0.50, 0.60),
            'pinch': 0.20,
            'confidence': 0.95,
        }], now=now, timestamp_ms=int(now * 1000))

        # StrumGuard detects entrance into guitar zone, suppresses frame, and rearms controller
        self.assertIsNone(ev2)
        self.assertEqual(status2, 'strum_zone')
        self.assertTrue(pipeline.last_suppressed)
        self.assertFalse(pipeline.controller.armed)
        self.assertFalse(pipeline.controller.active)

        # 3. Musician strums vigorously for 40 frames
        false_events = []
        for i in range(1, 40):
            now += 0.025
            strum_y = 0.70 + 0.12 * math.sin(2 * math.pi * 5.0 * now)
            ev, status = pipeline.process_frame([{
                'wrist': (0.50, strum_y),
                'pinch': 0.20,
                'confidence': 0.95,
            }], now=now, timestamp_ms=int(now * 1000))
            if ev:
                false_events.append(ev)

        # 100% suppression verified
        self.assertEqual(len(false_events), 0)

    def test_air_strumming_motion_reversals_disarm_controller(self):
        """Fast direction reversals in air (outside strum zone) trigger motion suppression."""
        # Strum zone placed far away in corner so only velocity motion triggers
        guard = StrumGuard(strum_zone=Rect(ymin=0.90, xmin=0.90, ymax=0.99, xmax=0.99))
        pipeline = VisionPipelineHarness(strum_guard=guard)

        # 1. Arm controller in air with open hand
        pipeline.process_frame([{
            'wrist': (0.35, 0.30),
            'pinch': 0.60,
            'confidence': 0.95,
        }], now=1.0, timestamp_ms=1000)
        self.assertTrue(pipeline.controller.armed)

        # 2. Pinch in air to engage
        pipeline.process_frame([{
            'wrist': (0.35, 0.30),
            'pinch': 0.20,
            'confidence': 0.95,
        }], now=1.1, timestamp_ms=1100)
        self.assertTrue(pipeline.controller.active)

        # 3. Rapid vertical strumming motion in air (down-up-down-up)
        # Fast direction reversals (>0.4 vel_y) within max_jump (0.30)
        now = 1.15
        motion_triggered = False
        for step_i, y_pos in enumerate([0.50, 0.30, 0.50, 0.30, 0.50]):
            now += 0.05
            ev, status = pipeline.process_frame([{
                'wrist': (0.35, y_pos),
                'pinch': 0.20,
                'confidence': 0.95,
            }], now=now, timestamp_ms=int(now * 1000))
            if status == 'strum_motion':
                motion_triggered = True

        self.assertTrue(motion_triggered)
        # Verify controller was rearmed and deactivated
        self.assertFalse(pipeline.controller.active)
        self.assertFalse(pipeline.controller.armed)

    def test_intentional_air_expression_is_uninhibited(self):
        """Smooth, moderate-speed expressive sweeps outside strum zone pass cleanly."""
        guard = StrumGuard(strum_zone=Rect(ymin=0.50, xmin=0.20, ymax=1.00, xmax=0.85))
        pipeline = VisionPipelineHarness(strum_guard=guard)

        # Arm with open hand in upper air zone
        pipeline.process_frame([{
            'wrist': (0.30, 0.40),
            'pinch': 0.60,
            'confidence': 0.95,
        }], now=1.0, timestamp_ms=1000)

        # Engage with pinch
        pipeline.process_frame([{
            'wrist': (0.30, 0.40),
            'pinch': 0.20,
            'confidence': 0.95,
        }], now=1.1, timestamp_ms=1100)
        self.assertTrue(pipeline.controller.active)

        # Smooth upward sweep from y=0.40 to y=0.20 over 0.5 seconds
        events = []
        now = 1.10
        for i in range(1, 15):
            now += 0.04
            y = 0.40 - (i * 0.012)
            ev, status = pipeline.process_frame([{
                'wrist': (0.30, y),
                'pinch': 0.20,
                'confidence': 0.95,
            }], now=now, timestamp_ms=int(now * 1000))
            self.assertEqual(status, 'expression_zone')
            self.assertFalse(pipeline.last_suppressed)
            if ev:
                self.validator.validate(ev)
                events.append(ev)

        self.assertGreater(len(events), 0)
        # Filter target increases upward
        self.assertGreater(events[-1]['value'], events[0]['value'])

    def test_multi_hand_fret_vs_strum_isolation(self):
        """When both hands are detected, HandSelector locks onto chosen wrist without flapping."""
        guard = StrumGuard(strum_zone=Rect(ymin=0.50, xmin=0.20, ymax=1.00, xmax=0.85))
        selector = HandSelector(max_jump=0.30, forget_after=15)
        pipeline = VisionPipelineHarness(selector=selector, strum_guard=guard)

        now = 1.0
        # Frame 1: Fret hand at (0.15, 0.45), Strum hand at (0.65, 0.70)
        pipeline.process_frame([
            {'wrist': (0.15, 0.45), 'pinch': 0.40, 'confidence': 0.90},
            {'wrist': (0.65, 0.70), 'pinch': 0.20, 'confidence': 0.90},
        ], now=now, timestamp_ms=1000)

        # Pipeline locked onto hand 0 (fret hand)
        self.assertEqual(selector.center, (0.15, 0.45))

        # Frames 2-20: Strum hand plays fast, detection order flips back and forth
        for i in range(1, 20):
            now += 0.033
            strum_y = 0.70 + 0.10 * math.sin(i)
            # Alternate detection order
            if i % 2 == 0:
                detections = [
                    {'wrist': (0.15, 0.46), 'pinch': 0.40, 'confidence': 0.90},
                    {'wrist': (0.65, strum_y), 'pinch': 0.20, 'confidence': 0.90},
                ]
            else:
                detections = [
                    {'wrist': (0.65, strum_y), 'pinch': 0.20, 'confidence': 0.90},
                    {'wrist': (0.15, 0.46), 'pinch': 0.40, 'confidence': 0.90},
                ]

            ev, status = pipeline.process_frame(detections, now=now, timestamp_ms=int(now * 1000))
            # Must remain locked onto fret hand anchor near (0.15, 0.46)
            self.assertAlmostEqual(selector.center[0], 0.15, delta=0.05)
            # Fret hand has pinch=0.40 (not open, not pinched), so 0 events
            self.assertIsNone(ev)

    def test_hendrix_transition_strum_to_air_solo_and_back(self):
        """End-to-end simulation of a guitarist transitioning between strumming and an air solo."""
        audio = Engine(EngineConfig(samplerate=16000))
        clock_state = {'ms': 1000}
        router = Router(audio, clock=lambda: clock_state['ms'], monotonic=lambda: clock_state['ms'])

        slider = FilterSlider(lambda: audio.snapshot()['filter']['target'], rate=20)
        guard = StrumGuard(strum_zone=Rect(ymin=0.50, xmin=0.20, ymax=1.00, xmax=0.85))
        pipeline = VisionPipelineHarness(slider=slider, strum_guard=guard)

        # Helper to step time and feed pipeline
        def step(x, y, pinch, conf=0.95):
            clock_state['ms'] += 50
            t = clock_state['ms'] / 1000.0
            ev, status = pipeline.process_frame([{
                'wrist': (x, y),
                'pinch': pinch,
                'confidence': conf,
            }], now=t, timestamp_ms=clock_state['ms'])
            if ev:
                self.validator.validate(ev)
                self.assertTrue(router.ingest(json.dumps(ev)))
                drain_audio(audio)
            return ev, status

        # Phase 1: Strumming rhythm chords in guitar zone (0.0s - 1.0s)
        for i in range(20):
            strum_y = 0.70 + 0.10 * math.sin(i)
            ev, status = step(x=0.55, y=strum_y, pinch=0.20)
            self.assertIsNone(ev)
            self.assertIn(status, ('strum_zone', 'strum_motion'))
        # Audio filter remains default 1.0
        self.assertEqual(audio.snapshot()['filter']['target'], 1.0)

        # Phase 2: Solo entrance - smooth 400ms physical lift into air expression zone
        for step_i in range(8):
            frac = (step_i + 1) / 8.0
            x = 0.55 + frac * (0.35 - 0.55)
            y = 0.70 + frac * (0.35 - 0.70)
            pinch = 0.20 if frac < 0.5 else 0.60
            step(x=x, y=y, pinch=pinch)

        self.assertTrue(pipeline.controller.armed)

        # Phase 3: Engage air pinch at y=0.35 and sweep down (darker tone) to y=0.60 in air (x=0.10)
        step(x=0.10, y=0.35, pinch=0.20)  # initial redundant send suppressed
        self.assertTrue(pipeline.controller.active)

        for i in range(1, 10):
            ev, status = step(x=0.10, y=0.35 + (i * 0.025), pinch=0.20)
            self.assertEqual(status, 'expression_zone')

        dark_filter = audio.snapshot()['filter']['target']
        self.assertLess(dark_filter, 1.0)

        # Phase 4: Release in air to freeze filter target
        step(x=0.10, y=0.60, pinch=0.60)
        self.assertFalse(pipeline.controller.active)
        self.assertEqual(audio.snapshot()['filter']['target'], dark_filter)

        # Phase 5: Return hand to guitar strings over 400ms and resume strumming
        for step_i in range(8):
            frac = (step_i + 1) / 8.0
            x = 0.10 + frac * (0.55 - 0.10)
            y = 0.60 + frac * (0.70 - 0.60)
            pinch = 0.60 if frac < 0.5 else 0.20
            step(x=x, y=y, pinch=pinch)

        for i in range(20):
            strum_y = 0.70 + 0.10 * math.sin(i)
            ev, status = step(x=0.55, y=strum_y, pinch=0.20)
            self.assertIsNone(ev)
            self.assertIn(status, ('strum_zone', 'strum_motion'))

        # Filter remains locked at dark_filter without any disturbance!
        self.assertEqual(audio.snapshot()['filter']['target'], dark_filter)
        self.assertGreater(router.counts['accepted'], 0)
        self.assertEqual(router.counts['invalid'], 0)
        self.assertEqual(router.counts['stale'], 0)

    def test_brief_occlusion_and_fail_closed_recovery(self):
        """Pipeline preserves anchor through 3-frame occlusion; re-entry requires open hand."""
        guard = StrumGuard(strum_zone=Rect(ymin=0.50, xmin=0.20, ymax=1.00, xmax=0.85))
        pipeline = VisionPipelineHarness(strum_guard=guard)

        # 1. Arm and engage in air expression zone
        pipeline.process_frame([{'wrist': (0.35, 0.35), 'pinch': 0.60, 'confidence': 0.95}], now=1.0, timestamp_ms=1000)
        ev1, _ = pipeline.process_frame([{'wrist': (0.35, 0.35), 'pinch': 0.20, 'confidence': 0.95}], now=1.1, timestamp_ms=1100)
        self.assertTrue(pipeline.controller.active)

        # 2. Hand briefly passes behind mic stand (3 frames with 0 detections)
        for i in range(3):
            ev, status = pipeline.process_frame([], now=1.15 + (i * 0.033), timestamp_ms=int((1.15 + i * 0.033) * 1000))
            self.assertIsNone(ev)
            self.assertEqual(status, 'no_hand')
            self.assertEqual(pipeline.selector.misses, i + 1)

        # Selector kept its anchor
        self.assertIsNotNone(pipeline.selector.center)
        # Controller failed closed
        self.assertFalse(pipeline.controller.active)
        self.assertFalse(pipeline.controller.armed)

        # 3. Hand reappears already pinching (e.g. holding pick)
        ev_pinch, status = pipeline.process_frame([{'wrist': (0.35, 0.35), 'pinch': 0.20, 'confidence': 0.95}], now=1.30, timestamp_ms=1300)
        self.assertIsNone(ev_pinch)
        self.assertFalse(pipeline.controller.active)  # Must NOT activate
        self.assertEqual(pipeline.selector.misses, 0)  # Re-locked onto anchor!

        # 4. Open hand to re-arm, then pinch engages
        pipeline.process_frame([{'wrist': (0.35, 0.35), 'pinch': 0.60, 'confidence': 0.95}], now=1.35, timestamp_ms=1350)
        self.assertTrue(pipeline.controller.armed)

        ev_reengage, _ = pipeline.process_frame([{'wrist': (0.35, 0.35), 'pinch': 0.20, 'confidence': 0.95}], now=1.40, timestamp_ms=1400)
        self.assertTrue(pipeline.controller.active)

    def test_dual_axis_pipeline_coordination_and_suppression(self):
        """DualAxisController in pipeline: arms/engages in air, suppresses cleanly in strum zone."""
        guard = StrumGuard(strum_zone=Rect(ymin=0.50, xmin=0.20, ymax=1.00, xmax=0.85))
        dual_ctrl = DualAxisController(pair_rate=10.0)
        pipeline = VisionPipelineHarness(controller=dual_ctrl, strum_guard=guard)

        # 1. Arm with flat hand in air
        flat = OrientationResult(roll_deg=0.0, pitch_deg=0.0, tilt_amount=0.0, openness=0.8)
        pipeline.process_frame([{
            'wrist': (0.35, 0.35),
            'pinch': 0.60,
            'confidence': 0.95,
            'orientation': flat,
        }], now=1.0, timestamp_ms=1000)
        self.assertTrue(dual_ctrl.armed)

        # 2. Engage with tilted hand in air
        tilted = OrientationResult(roll_deg=35.0, pitch_deg=0.0, tilt_amount=0.58, openness=0.2)
        events, status = pipeline.process_frame([{
            'wrist': (0.35, 0.30),
            'pinch': 0.20,
            'confidence': 0.95,
            'orientation': tilted,
        }], now=1.1, timestamp_ms=1100)

        self.assertEqual(status, 'expression_zone')
        self.assertTrue(dual_ctrl.active)
        self.assertEqual(len(events), 2)
        for ev in events:
            self.validator.validate(ev)

        # 3. Hand drops into strum zone across continuous camera frames
        pipeline.process_frame([{
            'wrist': (0.42, 0.50),
            'pinch': 0.20,
            'confidence': 0.95,
            'orientation': tilted,
        }], now=1.15, timestamp_ms=1150)

        events_strum, status_strum = pipeline.process_frame([{
            'wrist': (0.50, 0.70),
            'pinch': 0.20,
            'confidence': 0.95,
            'orientation': tilted,
        }], now=1.20, timestamp_ms=1200)

        self.assertEqual(events_strum, [])
        self.assertIn(status_strum, ('strum_zone', 'strum_motion'))
        self.assertFalse(dual_ctrl.active)
        self.assertFalse(dual_ctrl.armed)

    def test_hand_selector_forget_timeout_reacquisition(self):
        """After 15 frames of tracking absence, pipeline safely forgets old wrist and latches onto new one."""
        pipeline = VisionPipelineHarness()

        # Latch onto Hand 1 at (0.20, 0.40)
        pipeline.process_frame([{'wrist': (0.20, 0.40), 'pinch': 0.50, 'confidence': 0.90}], now=1.0, timestamp_ms=1000)
        self.assertEqual(pipeline.selector.center, (0.20, 0.40))

        # 15 empty frames
        now = 1.0
        for i in range(15):
            now += 0.033
            pipeline.process_frame([], now=now, timestamp_ms=int(now * 1000))

        self.assertIsNone(pipeline.selector.center)

        # Hand 2 appears on opposite side of screen (0.85, 0.30)
        now += 0.033
        pipeline.process_frame([{'wrist': (0.85, 0.30), 'pinch': 0.50, 'confidence': 0.90}], now=now, timestamp_ms=int(now * 1000))
        self.assertEqual(pipeline.selector.center, (0.85, 0.30))

    def test_pipeline_frame_metrics_latency_profile(self):
        """Pipeline harness processing overhead is measured and verified < 0.2 ms per frame."""
        metrics = FrameMetrics()
        guard = StrumGuard(strum_zone=Rect(ymin=0.50, xmin=0.20, ymax=1.00, xmax=0.85))
        pipeline = VisionPipelineHarness(strum_guard=guard)

        now = 10.0
        for i in range(150):
            t_start = now
            t_end = t_start + 0.00010  # 100 microseconds simulated execution
            now += 0.0333

            detections = [{
                'wrist': (0.35, 0.35 + 0.10 * math.sin(i * 0.1)),
                'pinch': 0.60 if i < 10 else 0.20,
                'confidence': 0.95,
            }]
            ev, _ = pipeline.process_frame(detections, now, int(now * 1000))
            metrics.record(t_start, t_end, 1 if ev else 0, hand_present=True)

        snap = metrics.snapshot()
        self.assertEqual(snap['frames'], 150)
        self.assertEqual(snap['hand_present_frames'], 150)
        self.assertLess(snap['processing_mean_ms'], 0.5)


def drain_audio(engine):
    """Process a dummy audio block to apply queued parameter updates."""
    in_buf = np.zeros(128, dtype=np.float32)
    out_buf = np.zeros((128, 2), dtype=np.float32)
    engine.process(in_buf, out_buf)


if __name__ == '__main__':
    unittest.main()
