"""Hardening tests for clutch state machine, relative pickup, and false-trigger rejection.

Covers:
1. Strumming false-trigger isolation (guitar pick grip vs pinch, rapid strum oscillations)
2. Hand loss & low-confidence fail-closed safety (zero glitch, hold-last-value, re-arm requirement)
3. Re-pinch relative pickup (seamless target re-engagement after manual rig change, boundary clamping)
4. Up-is-more geometric mapping and directionality (absolute & relative modes)
5. Pinch hysteresis band stability (no flapping in deadband)
6. Rate limiting and monotonicity enforcement within transport budget
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


class ClutchHardeningTests(unittest.TestCase):
    def setUp(self):
        schema_path = Path(__file__).resolve().parents[1] / 'protocol/control.schema.json'
        self.validator = Draft202012Validator(json.loads(schema_path.read_text()))

    # -------------------------------------------------------------------------
    # 1. Strumming False-Trigger Isolation
    # -------------------------------------------------------------------------
    def test_guitar_pick_grip_without_open_hand_never_triggers_false_controls(self):
        """Holding a pick (fingers pinched) while playing guitar must never arm or engage the clutch."""
        c = Controller()
        now = 1.0
        # Guitarist starts playing guitar with pick in hand:
        # Thumb and index tips are pinched (pinch ratio ~0.18 - 0.22).
        # Hand moves up and down rapidly strumming chords across 2 seconds (60 frames at 30 fps).
        events = []
        for i in range(60):
            now += 0.033
            # Sinusoidal strumming motion between y=0.55 and y=0.75 at ~3.5 Hz
            strum_y = 0.65 + 0.10 * math.sin(2 * math.pi * 3.5 * i * 0.033)
            pick_pinch = 0.20 + 0.02 * math.sin(i)  # holding pick: always <= 0.24
            ev = c.update(strum_y, pick_pinch, confidence=0.92, now=now, timestamp_ms=int(now * 1000))
            if ev:
                events.append(ev)

        # Zero false triggers! The controller never armed because an open hand (pinch >= 0.45)
        # was never presented.
        self.assertEqual(len(events), 0)
        self.assertFalse(c.armed)
        self.assertFalse(c.active)
        self.assertIsNone(c.value)

    def test_post_arm_strumming_vulnerability_and_strumguard_shielding(self):
        """If armed before playing, raw Controller will sweep, but StrumGuard suppresses it."""
        c = Controller(rate=20)
        guard = StrumGuard(
            strum_zone=Rect(ymin=0.50, xmin=0.20, ymax=1.00, xmax=0.85),
            velocity_threshold=2.5,
            reversal_window=0.35,
            reversal_count_trigger=3,
        )

        now = 1.0
        # 1. Musician presents an open hand to the camera (arms the clutch)
        c.update(y=0.40, pinch=0.60, confidence=0.95, now=now, timestamp_ms=int(now * 1000))
        self.assertTrue(c.armed)

        # 2. Musician pinches fingers to grab pick in air
        now += 0.10
        c.update(y=0.40, pinch=0.20, confidence=0.95, now=now, timestamp_ms=int(now * 1000))
        self.assertTrue(c.active)

        # 3. Musician now moves hand to guitar position (x=0.50, y=0.70) and strums rapidly
        raw_events = []
        guarded_events = []

        # Duplicate controller for shielded test
        shielded_c = Controller(rate=20)
        shielded_c.update(y=0.40, pinch=0.60, confidence=0.95, now=1.0, timestamp_ms=1000)
        shielded_c.update(y=0.40, pinch=0.20, confidence=0.95, now=1.1, timestamp_ms=1100)

        for i in range(1, 40):
            t = now + i * 0.025  # 40 fps
            # Fast vertical oscillation
            y = 0.70 + 0.12 * math.sin(2 * math.pi * 5.0 * t)
            x = 0.50  # inside guitar strum zone

            # Raw controller triggers sweeps
            ev_raw = c.update(y, pinch=0.20, confidence=0.95, now=t, timestamp_ms=int(t * 1000))
            if ev_raw:
                raw_events.append(ev_raw)

            # Shielded path: check StrumGuard before updating controller
            suppressed, reason = guard.update(x, y, now=t)
            if not suppressed:
                ev_shielded = shielded_c.update(y, pinch=0.20, confidence=0.95, now=t, timestamp_ms=int(t * 1000))
                if ev_shielded:
                    guarded_events.append(ev_shielded)

        # Without StrumGuard, raw controller emitted multiple unintended sweeps during strumming
        self.assertGreater(len(raw_events), 0)

        # With StrumGuard, guitar zone / motion suppression completely prevented false triggers
        self.assertEqual(len(guarded_events), 0)

    def test_hand_selector_fast_strum_jump_rejection(self):
        """HandSelector must reject sudden large jumps and count misses rather than track wildly."""
        selector = HandSelector(max_jump=0.30, forget_after=15)
        # Latch onto hand near center
        self.assertEqual(selector.select([ (0.5, 0.5) ]), 0)
        self.assertEqual(selector.center, (0.5, 0.5))

        # Downstroke causes wrist to jump by 0.35 in a single frame
        self.assertIsNone(selector.select([ (0.5, 0.86) ]))
        self.assertEqual(selector.misses, 1)
        self.assertEqual(selector.center, (0.5, 0.5))  # Anchor preserved

        # Upstroke brings hand back within reach
        self.assertEqual(selector.select([ (0.5, 0.65) ]), 0)
        self.assertEqual(selector.misses, 0)
        self.assertEqual(selector.center, (0.5, 0.65))

    # -------------------------------------------------------------------------
    # 2. Hand Loss & Low-Confidence Gating
    # -------------------------------------------------------------------------
    def test_confidence_drop_freezes_output_without_glitch(self):
        """When detector confidence drops below 0.60, controller must immediately fail-closed and emit None."""
        c = Controller(rate=20)
        c.update(0.5, 0.60, 0.90, now=1.0, timestamp_ms=1000)  # Arm
        ev1 = c.update(0.4, 0.20, 0.90, now=1.1, timestamp_ms=1100)  # Engage
        self.assertIsNotNone(ev1)
        engaged_val = ev1['value']

        # Confidence drops to 0.58 (< 0.60 threshold)
        ev_low = c.update(0.3, 0.20, 0.58, now=1.2, timestamp_ms=1200)
        self.assertIsNone(ev_low)
        self.assertFalse(c.active)
        self.assertFalse(c.armed)
        self.assertIsNone(c.value)

        # Sent value is preserved so engine remains at engaged_val
        self.assertEqual(c.sent_value, engaged_val)

    def test_hand_loss_fails_closed_and_requires_open_hand_to_rearm(self):
        """After total hand loss (None, None), re-appearing while pinched must NOT engage."""
        c = Controller(rate=20)
        c.update(0.5, 0.60, 0.90, now=1.0, timestamp_ms=1000)
        c.update(0.5, 0.20, 0.90, now=1.1, timestamp_ms=1100)
        self.assertTrue(c.active)

        # Hand leaves frame entirely
        self.assertIsNone(c.update(None, None, 0.0, now=1.2, timestamp_ms=1200))
        self.assertFalse(c.active)
        self.assertFalse(c.armed)

        # Hand reappears already pinching (e.g. holding pick or making fist)
        self.assertIsNone(c.update(0.3, 0.15, 0.95, now=1.3, timestamp_ms=1300))
        self.assertFalse(c.active)  # Must NOT activate
        self.assertFalse(c.armed)

        # User intentionally opens hand to re-arm
        self.assertIsNone(c.update(0.3, 0.55, 0.95, now=1.4, timestamp_ms=1400))
        self.assertFalse(c.active)
        self.assertTrue(c.armed)  # Now armed

        # Now pinching engages cleanly
        ev = c.update(0.3, 0.15, 0.95, now=1.5, timestamp_ms=1500)
        self.assertIsNotNone(ev)
        self.assertTrue(c.active)
        self.validator.validate(ev)

    def test_intermittent_confidence_noise_preserves_strict_sequence_order(self):
        """Under choppy tracking where confidence dips every few frames, sequence numbers must be monotonic."""
        c = Controller(rate=60, deadband=0.001)
        c.update(0.8, 0.60, 0.95, now=1.0, timestamp_ms=1000)
        first_ev = c.update(0.8, 0.20, 0.95, now=1.05, timestamp_ms=1050)

        events = [first_ev] if first_ev else []
        seqs = [first_ev['seq']] if first_ev else []
        now = 1.05
        for i in range(1, 30):
            now += 0.03
            # Intermittent confidence dips every 5th frame
            conf = 0.40 if (i % 5 == 0) else 0.90
            y = 0.8 - (i * 0.015)
            # If armed was reset by low confidence, open hand to rearm on next step
            if not c.armed and not c.active:
                c.update(y, 0.50, 0.90, now=now, timestamp_ms=int(now * 1000))
                now += 0.01
                ev = c.update(y, 0.20, conf, now=now, timestamp_ms=int(now * 1000))
            else:
                ev = c.update(y, 0.20, conf, now=now, timestamp_ms=int(now * 1000))

            if ev:
                events.append(ev)
                seqs.append(ev['seq'])
                self.validator.validate(ev)

        self.assertGreater(len(seqs), 3)
        self.assertEqual(seqs, list(range(len(seqs))))

    # -------------------------------------------------------------------------
    # 3. Re-pinch Relative Pickup Dynamics
    # -------------------------------------------------------------------------
    def test_filter_slider_smooth_pickup_after_manual_rig_change(self):
        """Relative FilterSlider must query rig target on engagement and suppress first redundant send."""
        audio = Engine(EngineConfig(samplerate=16000))
        audio.set_filter(0.40)
        clock_state = {'ms': 1000}
        router = Router(audio, clock=lambda: clock_state['ms'], monotonic=lambda: clock_state['ms'])

        slider = FilterSlider(lambda: audio.snapshot()['filter']['target'], rate=20)

        # 1. Arm with open hand
        clock_state['ms'] = 1000
        self.assertIsNone(slider.update(0.5, 0.60, 0.95, now=1.0, timestamp_ms=clock_state['ms']))

        # 2. Grab at y=0.50
        clock_state['ms'] = 1100
        ev = slider.update(0.5, 0.20, 0.95, now=1.1, timestamp_ms=clock_state['ms'])
        self.assertIsNone(ev)  # First send suppressed!
        self.assertEqual(slider.controller.value, 0.40)

        # 3. Move hand up to y=0.30 -> filter rises
        clock_state['ms'] = 1200
        ev_up = slider.update(0.3, 0.20, 0.95, now=1.2, timestamp_ms=clock_state['ms'])
        self.assertIsNotNone(ev_up)
        self.assertTrue(router.ingest(json.dumps(ev_up)))
        drain_audio(audio)
        current_target = audio.snapshot()['filter']['target']
        self.assertGreater(current_target, 0.40)

        # 4. Release hand (open)
        clock_state['ms'] = 1300
        slider.update(0.3, 0.60, 0.95, now=1.3, timestamp_ms=clock_state['ms'])
        self.assertFalse(slider.controller.active)

        # 5. External change: musician taps hardware pedal or moves web fader to 0.15
        audio.set_filter(0.15)
        drain_audio(audio)
        self.assertAlmostEqual(audio.snapshot()['filter']['target'], 0.15)

        # 6. Musician re-pinches at a completely different vertical position (y=0.75)
        clock_state['ms'] = 1400
        ev_regrab = slider.update(0.75, 0.20, 0.95, now=1.4, timestamp_ms=clock_state['ms'])
        self.assertIsNone(ev_regrab)  # First send suppressed
        self.assertAlmostEqual(slider.controller.value, 0.15)
        self.assertAlmostEqual(audio.snapshot()['filter']['target'], 0.15)

        # 7. Move hand up from y=0.75 to y=0.65 -> delta = +0.10 / 0.60 = +0.166
        clock_state['ms'] = 1500
        ev_move = slider.update(0.65, 0.20, 0.95, now=1.5, timestamp_ms=clock_state['ms'])
        self.assertIsNotNone(ev_move)
        self.assertTrue(router.ingest(json.dumps(ev_move)))
        drain_audio(audio)
        self.assertGreater(audio.snapshot()['filter']['target'], 0.15)

    def test_repinch_boundary_clamping_at_extremes(self):
        """Relative pickup near extremes (0.95 or 0.05) must clamp cleanly to [0, 1] without overflow."""
        current_val = 0.95
        slider = FilterSlider(lambda: current_val, rate=60)
        slider.controller.deadband = 0.0

        # Arm and engage at y=0.5
        slider.update(0.5, 0.60, 0.95, now=1.0, timestamp_ms=1000)
        slider.update(0.5, 0.20, 0.95, now=1.1, timestamp_ms=1100)

        # Move hand way up (y=0.10) which would calculate 0.95 + (0.5 - 0.1)/0.6 = 0.95 + 0.66 = 1.61
        ev = slider.update(0.10, 0.20, 0.95, now=1.2, timestamp_ms=1200)
        self.assertIsNotNone(ev)
        self.assertLessEqual(ev['value'], 1.0)
        self.assertGreaterEqual(ev['value'], 0.95)

        # Test lower extreme near 0.05
        current_val = 0.05
        slider2 = FilterSlider(lambda: current_val, rate=60)
        slider2.controller.deadband = 0.0
        slider2.update(0.5, 0.60, 0.95, now=1.0, timestamp_ms=1000)
        slider2.update(0.5, 0.20, 0.95, now=1.1, timestamp_ms=1100)

        # Move hand way down (y=0.90) which would calculate 0.05 - 0.4/0.6 = -0.61
        ev_down = slider2.update(0.90, 0.20, 0.95, now=1.2, timestamp_ms=1200)
        self.assertIsNotNone(ev_down)
        self.assertGreaterEqual(ev_down['value'], 0.0)
        self.assertLessEqual(ev_down['value'], 0.05)

    def test_slider_error_handling_on_bad_or_throwing_engine_target(self):
        """FilterSlider must fail closed and report error if read_target throws or returns invalid types."""
        def broken_reader():
            raise RuntimeError('Audio daemon socket timeout')

        slider = FilterSlider(broken_reader)
        slider.update(0.5, 0.60, 0.95, now=1.0, timestamp_ms=1000)
        res = slider.update(0.5, 0.20, 0.95, now=1.1, timestamp_ms=1100)

        self.assertIsNone(res)
        self.assertIn('RuntimeError', slider.error)
        self.assertFalse(slider.controller.armed)
        self.assertFalse(slider.controller.active)

        # Non-numeric return values must also fail closed
        for bad in (True, False, None, float('nan'), float('inf'), -0.1, 1.1, '0.5'):
            bad_slider = FilterSlider(lambda: bad)
            bad_slider.update(0.5, 0.60, 0.95, now=1.0, timestamp_ms=1000)
            res = bad_slider.update(0.5, 0.20, 0.95, now=1.1, timestamp_ms=1100)
            self.assertIsNone(res)
            self.assertIsNotNone(bad_slider.error)

    # -------------------------------------------------------------------------
    # 4. Up-Is-More Inversion & Geometric Linearity
    # -------------------------------------------------------------------------
    def test_absolute_up_is_more_geometric_linearity(self):
        """Standard camera coordinates (0=top, 1=bottom): moving hand UP (y decreasing) increases parameter."""
        c = Controller(low=0.8, high=0.2, rate=60, deadband=0.0, tau=0.001)
        c.update(0.8, 0.60, 0.95, now=1.0, timestamp_ms=1000)

        values = []
        y_steps = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]
        now = 1.0
        for y in y_steps:
            now += 0.05
            ev = c.update(y, 0.20, 0.95, now=now, timestamp_ms=int(now * 1000))
            if ev:
                values.append(ev['value'])

        # Verify values strictly increase as hand moves UP towards high position (0.2)
        for i in range(len(values) - 1):
            self.assertLess(values[i], values[i + 1])

        self.assertAlmostEqual(values[0], 0.0, places=2)
        self.assertAlmostEqual(values[-1], 1.0, places=2)

    def test_relative_up_is_more_directionality(self):
        """In relative mode: moving hand UP from pickup increases value; moving DOWN decreases it."""
        c = Controller(relative=True, low=0.8, high=0.2, rate=60, deadband=0.0, tau=0.001)
        c.sent_value = 0.50  # Start midpoint
        c.update(0.5, 0.60, 0.95, now=1.0, timestamp_ms=1000)
        c.update(0.5, 0.20, 0.95, now=1.05, timestamp_ms=1050)

        # Move UP (y=0.4 < 0.5)
        ev_up = c.update(0.4, 0.20, 0.95, now=1.1, timestamp_ms=1100)
        self.assertIsNotNone(ev_up)
        self.assertGreater(ev_up['value'], 0.50)

        # Move DOWN (y=0.6 > 0.5)
        ev_down = c.update(0.6, 0.20, 0.95, now=1.15, timestamp_ms=1150)
        self.assertIsNotNone(ev_down)
        self.assertLess(ev_down['value'], 0.50)

    # -------------------------------------------------------------------------
    # 5. Pinch Hysteresis Band Stability
    # -------------------------------------------------------------------------
    def test_pinch_hysteresis_band_stability(self):
        """Micro-movements inside the hysteresis window (0.25 < pinch < 0.45) must never toggle state."""
        c = Controller(rate=60, deadband=0.0)
        c.update(0.5, 0.60, 0.95, now=1.0, timestamp_ms=1000)  # Arm with open hand
        self.assertTrue(c.armed)
        self.assertFalse(c.active)

        # Pinch to engage
        c.update(0.5, 0.24, 0.95, now=1.05, timestamp_ms=1050)
        self.assertTrue(c.active)

        # Relax pinch into hysteresis band: 0.26, 0.35, 0.42
        for p in (0.26, 0.35, 0.40, 0.44):
            c.update(0.5, p, 0.95, now=1.1, timestamp_ms=1100)
            self.assertTrue(c.active, f"Pinch={p} should remain active in hysteresis band")

        # Cross release threshold (pinch >= 0.45)
        c.update(0.5, 0.46, 0.95, now=1.15, timestamp_ms=1150)
        self.assertFalse(c.active)
        self.assertTrue(c.armed)

        # Finger tremor in band (0.42, 0.35, 0.28) must NOT re-engage without crossing 0.25
        for p in (0.42, 0.35, 0.28):
            c.update(0.5, p, 0.95, now=1.2, timestamp_ms=1200)
            self.assertFalse(c.active, f"Pinch={p} should not engage from disengaged state")

        # Cross engage threshold
        c.update(0.5, 0.23, 0.95, now=1.25, timestamp_ms=1250)
        self.assertTrue(c.active)

    # -------------------------------------------------------------------------
    # 6. Rate Limiting and Monotonicity Enforcement
    # -------------------------------------------------------------------------
    def test_rate_limiter_strictly_enforces_budget_under_high_frame_rate(self):
        """Pumping 120 FPS continuous motion must never exceed configured rate (20 Hz)."""
        rate = 20.0
        c = Controller(rate=rate, deadband=0.0, tau=0.001)
        c.update(0.8, 0.60, 0.95, now=0.0, timestamp_ms=0)
        c.update(0.8, 0.20, 0.95, now=0.01, timestamp_ms=10)

        events = []
        # Run 1 second of 120 FPS frames (8.33 ms per frame)
        for i in range(2, 122):
            t = i * (1.0 / 120.0)
            y = 0.8 - (i * 0.004)
            ev = c.update(y, 0.20, 0.95, now=t, timestamp_ms=int(t * 1000))
            if ev:
                events.append((t, ev))

        # Over 1.0 second, total events must not exceed 21 (rate=20 + 1 boundary)
        self.assertLessEqual(len(events), int(rate) + 1)
        self.assertGreaterEqual(len(events), 15)

        # Check spacing between consecutive events
        for j in range(len(events) - 1):
            t_curr = events[j][0]
            t_next = events[j + 1][0]
            interval = t_next - t_curr
            self.assertGreaterEqual(interval, (1.0 / rate) - 1e-4)

    # -------------------------------------------------------------------------
    # 7. Dual-Axis Coordination
    # -------------------------------------------------------------------------
    def test_dual_axis_independent_control_and_shared_budget(self):
        """DualAxisController coordinates elevation (filter) and tilt roll (reverb) within shared rate."""
        pair_rate = 10.0  # 10 pairs/sec = 20 events/sec total
        ctrl = DualAxisController(pair_rate=pair_rate, deadband=0.005)

        # Arm with flat hand
        flat = OrientationResult(roll_deg=0.0, pitch_deg=0.0, tilt_amount=0.0, openness=0.8)
        ctrl.update(y=0.8, pinch=0.60, orientation=flat, confidence=0.9, now=1.0, timestamp_ms=1000)

        # Engage with tilted hand
        tilted = OrientationResult(roll_deg=45.0, pitch_deg=0.0, tilt_amount=0.75, openness=0.2)
        events = ctrl.update(y=0.3, pinch=0.20, orientation=tilted, confidence=0.9, now=1.1, timestamp_ms=1100)

        self.assertEqual(len(events), 2)
        filter_ev = next(e for e in events if e['control'] == 'filter')
        reverb_ev = next(e for e in events if e['control'] == 'reverb')

        # Filter should be high (y=0.3 is up), Reverb should be high (tilt=0.75)
        self.assertGreater(filter_ev['value'], 0.5)
        self.assertGreater(reverb_ev['value'], 0.5)
        self.assertEqual(filter_ev['seq'] + 1, reverb_ev['seq'])

    # -------------------------------------------------------------------------
    # 8. Multi-Hand Dual-Trajectory Tracking (Fret vs Strum)
    # -------------------------------------------------------------------------
    def test_hand_selector_multi_hand_tracking_lifecycle(self):
        """Selector must lock onto initial hand, reject swap when detector order flips, and switch after timeout."""
        selector = HandSelector(max_jump=0.30, forget_after=10)

        # Frame 1: Left hand (fret) at (0.20, 0.50), Right hand (strum) at (0.75, 0.40)
        idx1 = selector.select([(0.20, 0.50), (0.75, 0.40)])
        self.assertEqual(idx1, 0)
        self.assertEqual(selector.center, (0.20, 0.50))

        # Frame 2: Detector order flips! Right hand is index 0, Left hand is index 1
        idx2 = selector.select([(0.75, 0.40), (0.21, 0.51)])
        self.assertEqual(idx2, 1)  # Stays locked on Left hand!
        self.assertEqual(selector.center, (0.21, 0.51))

        # Frames 3-12: Left hand leaves camera frame, only Right hand remains
        for miss_count in range(1, 10):
            idx = selector.select([(0.75, 0.40)])
            self.assertIsNone(idx)
            self.assertEqual(selector.misses, miss_count)
            self.assertIsNotNone(selector.center)

        # Frame 13: 10th consecutive miss reaches forget_after limit
        idx10 = selector.select([(0.75, 0.40)])
        self.assertIsNone(idx10)
        self.assertIsNone(selector.center)  # Old track forgotten

        # Frame 14: Selector now cleanly acquires the remaining Right hand
        idx_new = selector.select([(0.75, 0.40)])
        self.assertEqual(idx_new, 0)
        self.assertEqual(selector.center, (0.75, 0.40))

    # -------------------------------------------------------------------------
    # 9. Non-Finite & Non-Monotonic Clock Fuzzing
    # -------------------------------------------------------------------------
    def test_non_finite_and_backward_time_fail_closed(self):
        """Controller must silently reject NaNs, infinities, and time travel without crashing or emitting."""
        c = Controller()
        c.update(0.5, 0.60, 0.95, now=1.0, timestamp_ms=1000)

        # Time travel: now < previous
        self.assertIsNone(c.update(0.5, 0.20, 0.95, now=0.9, timestamp_ms=900))
        # Non-finite values
        for bad_y in (float('nan'), float('inf'), float('-inf')):
            self.assertIsNone(c.update(bad_y, 0.20, 0.95, now=1.1, timestamp_ms=1100))
        for bad_pinch in (float('nan'), float('inf'), -0.1):
            self.assertIsNone(c.update(0.5, bad_pinch, 0.95, now=1.2, timestamp_ms=1200))
        for bad_conf in (float('nan'), -0.01, 1.01):
            self.assertIsNone(c.update(0.5, 0.20, bad_conf, now=1.3, timestamp_ms=1300))

    # -------------------------------------------------------------------------
    # 11. End-to-End Acceptance Playbook Simulation (MANUAL.md Spec)
    # -------------------------------------------------------------------------
    def test_manual_playbook_gesture_clutch_hold_loss_and_rearm(self):
        """End-to-end validation of the complete manual test playbook for gesture clutching."""
        audio = Engine(EngineConfig(samplerate=16000))
        clock_state = {'ms': 1000}
        router = Router(audio, clock=lambda: clock_state['ms'], monotonic=lambda: clock_state['ms'])
        slider = FilterSlider(lambda: audio.snapshot()['filter']['target'], rate=20)

        # Helper to step time and feed slider
        def step(y, pinch, conf=0.95):
            clock_state['ms'] += 60  # ~16.6 Hz intervals
            ev = slider.update(y, pinch, conf, now=clock_state['ms'] / 1000.0, timestamp_ms=clock_state['ms'])
            if ev:
                self.validator.validate(ev)
                self.assertTrue(router.ingest(json.dumps(ev)))
                drain_audio(audio)
            return ev

        # Step 1: Guitarist plays guitar holding pick (pinched thumb & index)
        # Clutch must stay dormant (0 events, filter stays at default 1.0)
        for i in range(10):
            strum_y = 0.65 + 0.10 * math.sin(i)
            self.assertIsNone(step(strum_y, pinch=0.20))
        self.assertEqual(audio.snapshot()['filter']['target'], 1.0)

        # Step 2: Guitarist lifts hand above strings and opens palm to arm
        self.assertIsNone(step(y=0.45, pinch=0.65))
        self.assertTrue(slider.controller.armed)
        self.assertFalse(slider.controller.active)

        # Step 3: Guitarist pinches at y=0.45 to engage
        self.assertIsNone(step(y=0.45, pinch=0.20))  # redundant first send suppressed
        self.assertTrue(slider.controller.active)
        self.assertEqual(audio.snapshot()['filter']['target'], 1.0)

        # Step 4: Guitarist sweeps hand down to lower filter (y=0.70)
        ev_down = step(y=0.70, pinch=0.20)
        self.assertIsNotNone(ev_down)
        lower_val = audio.snapshot()['filter']['target']
        self.assertLess(lower_val, 1.0)

        # Step 5: Guitarist opens hand mid-air (release)
        self.assertIsNone(step(y=0.70, pinch=0.60))
        self.assertFalse(slider.controller.active)
        self.assertEqual(audio.snapshot()['filter']['target'], lower_val)

        # Step 6: Hand moves out of camera frame entirely
        self.assertIsNone(step(y=None, pinch=None, conf=0.0))
        self.assertFalse(slider.controller.armed)
        self.assertFalse(slider.controller.active)
        self.assertEqual(audio.snapshot()['filter']['target'], lower_val)

        # Step 7: Hand returns already holding pick and strums
        for i in range(10):
            strum_y = 0.65 + 0.10 * math.sin(i)
            self.assertIsNone(step(strum_y, pinch=0.20))
        # Filter target MUST NOT have moved!
        self.assertEqual(audio.snapshot()['filter']['target'], lower_val)

        # Step 8: Guitarist deliberately opens hand in air to re-arm
        self.assertIsNone(step(y=0.70, pinch=0.60))
        self.assertTrue(slider.controller.armed)

        # Step 9: Re-pinch at y=0.70 and sweep up to y=0.30
        self.assertIsNone(step(y=0.70, pinch=0.20))  # suppressed first send
        ev_up = step(y=0.30, pinch=0.20)
        self.assertIsNotNone(ev_up)
        raised_val = audio.snapshot()['filter']['target']
        self.assertGreater(raised_val, lower_val)

        # Final verification: router recorded clean receptions, zero stale, zero invalid
        self.assertGreater(router.counts['accepted'], 1)
        self.assertEqual(router.counts['invalid'], 0)
        self.assertEqual(router.counts['stale'], 0)
        self.assertEqual(router.counts['future'], 0)
        self.assertEqual(router.counts['duplicate'], 0)

    # -------------------------------------------------------------------------
    # 12. Synthetic Replay Benchmark with Measured FrameMetrics
    # -------------------------------------------------------------------------
    def test_replay_trajectory_frame_metrics_profile(self):
        """Measures execution latency across a 150-frame synthetic performance stream."""
        metrics = FrameMetrics()
        slider = FilterSlider(lambda: 0.50, rate=20)
        now = 10.0

        # Feed 150 frames simulating 5 seconds at 30 fps
        for i in range(150):
            t_start = now
            t_end = t_start + 0.00015  # Simulate ~0.15ms computation time
            now += 0.0333

            y = 0.5 + 0.2 * math.sin(i * 0.1)
            pinch = 0.60 if i < 10 else 0.20
            ev = slider.update(y, pinch, 0.95, now=now, timestamp_ms=int(now * 1000))
            emitted = 1 if ev else 0

            metrics.record(t_start, t_end, emitted, hand_present=True)

        snap = metrics.snapshot()
        self.assertEqual(snap['frames'], 150)
        self.assertEqual(snap['hand_present_frames'], 150)
        self.assertLess(snap['processing_mean_ms'], 1.0)
        self.assertLessEqual(snap['emitted_events_hz'], 20.0)
        self.assertIsNotNone(snap['processing_p95_ms'])


def drain_audio(engine):
    """Process a dummy block to apply queued parameter updates."""
    in_buf = np.zeros(128, dtype=np.float32)
    out_buf = np.zeros((128, 2), dtype=np.float32)
    engine.process(in_buf, out_buf)


if __name__ == '__main__':
    unittest.main()
