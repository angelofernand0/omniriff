import unittest
from pathlib import Path
import contextlib
import io
import json
import tempfile
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np

from vision.control import Controller
from vision.diagnostics import CameraDiagnostics
from vision.__main__ import main


class MissingHandGraceTests(unittest.TestCase):
    def engaged(self):
        control = Controller(relative=True, rate=60, deadband=0)
        control.update(.5, .6, .9, 1.0, 1000)
        self.assertIsNotNone(control.update(.5, .1, .9, 1.1, 1100))
        return control

    def test_brief_absence_holds_without_emitting_and_resumes(self):
        control = self.engaged()
        sent = control.seq
        self.assertIsNone(control.update(None, None, 0., 1.2, 1200, missing=True))
        self.assertTrue(control.active)
        self.assertEqual(control.seq, sent)
        self.assertIsNone(control.update(None, None, 0., 1.3, 1300, missing=True))
        self.assertEqual(control.seq, sent)
        resumed = control.update(.4, .1, .9, 1.31, 1310)
        self.assertIsNotNone(resumed)
        self.assertEqual(resumed['seq'], sent)
        self.assertTrue(control.active)

    def test_absence_over_grace_disarms_and_requires_open_hand(self):
        control = self.engaged()
        self.assertIsNone(control.update(None, None, 0., 1.2, 1200, missing=True))
        self.assertIsNone(control.update(None, None, 0., 1.36, 1360, missing=True))
        self.assertFalse(control.active)
        self.assertIsNone(control.update(.4, .1, .9, 1.4, 1400))
        control.update(.4, .6, .9, 1.5, 1500)
        self.assertIsNotNone(control.update(.4, .1, .9, 1.6, 1600))

    def test_reappearance_after_unobserved_gap_disarms(self):
        control = self.engaged()
        self.assertIsNone(control.update(.4, .1, .9, 1.4, 1400))
        self.assertFalse(control.active)

    def test_low_confidence_and_rejected_tracking_do_not_get_grace(self):
        control = self.engaged()
        self.assertIsNone(control.update(.5, .1, .2, 1.2, 1200, missing=False))
        self.assertFalse(control.active)
        control = self.engaged()
        self.assertIsNone(control.update(None, None, 0., 1.2, 1200, missing=False))
        self.assertFalse(control.active)

    def test_grace_does_not_arm_an_inactive_clutch(self):
        control = Controller()
        control.update(.5, .6, .9, 1., 1000)
        self.assertIsNone(control.update(None, None, 0., 1.1, 1100, missing=True))
        self.assertIsNone(control.update(.5, .1, .9, 1.2, 1200))

    def test_grace_bounds_are_validated(self):
        for value in (-.01, .31, float('nan')):
            with self.assertRaises(ValueError):
                Controller(missing_grace=value)


class CameraDiagnosticsTests(unittest.TestCase):
    def test_rolling_fps_lighting_and_dropout_counts(self):
        diagnostics = CameraDiagnostics(window=3)
        dark = np.zeros((32, 32, 3), dtype=np.uint8)
        light = np.full((32, 32, 3), 100, dtype=np.uint8)
        diagnostics.observe(dark, 1.0, True)
        diagnostics.observe(light, 1.1, False)
        diagnostics.observe(light, 1.2, False)
        diagnostics.observe(light, 1.3, True)
        snapshot = diagnostics.snapshot()
        self.assertAlmostEqual(snapshot['camera_fps'], 10.)
        self.assertAlmostEqual(snapshot['scene_brightness_0_255'], 48.8)
        self.assertEqual(snapshot['hand_present_frames'], 2)
        self.assertEqual(snapshot['hand_absent_frames'], 2)
        self.assertEqual(snapshot['presence_dropouts'], 1)
        self.assertEqual(snapshot['longest_absent_frames'], 2)


class NativeCaptureWiringTests(unittest.TestCase):
    def test_no_hand_frames_freeze_control_without_emitting(self):
        clock = [0.]

        class Capture:
            def __init__(self, *args):
                self.frames = 0

            def isOpened(self):
                return True

            def get(self, key):
                return 30

            def read(self):
                self.frames += 1
                clock[0] += 1 / 30
                return self.frames <= 6, np.full((48, 64, 3), 80, np.uint8)

            def release(self):
                pass

        class Detector:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def detect_for_video(self, *args):
                frame = round(clock[0] * 30)
                if frame in (3, 4):
                    return NS(hand_landmarks=[], handedness=[])
                points = [NS(x=.5, y=.5) for _ in range(21)]
                points[0] = NS(x=.5, y=.6 if frame >= 5 else .5)
                points[5], points[17] = NS(x=.3, y=.5), NS(x=.7, y=.5)
                points[4] = NS(x=.1 if frame == 1 else .48, y=.5)
                points[8] = NS(x=.5, y=.5)
                return NS(hand_landmarks=[points], handedness=[[NS(score=.95)]])

        cv = NS(VideoCapture=Capture, CAP_PROP_FPS=1, COLOR_BGR2RGB=1,
                cvtColor=lambda frame, mode: frame, destroyAllWindows=lambda: None)
        mp = NS(Image=lambda image_format, data: data, ImageFormat=NS(SRGB=1),
                tasks=NS(BaseOptions=lambda **kw: kw, vision=NS(
                    HandLandmarkerOptions=lambda **kw: kw, RunningMode=NS(VIDEO=1),
                    HandLandmarker=NS(create_from_options=lambda options: Detector()))))
        with tempfile.TemporaryDirectory() as folder:
            metrics_path = Path(folder) / 'metrics.json'
            output = io.StringIO()
            with patch.dict('sys.modules', {'cv2': cv, 'mediapipe': mp}), \
                    patch('vision.__main__.time.monotonic', side_effect=lambda: clock[0]), \
                    patch('vision.__main__.time.time', side_effect=lambda: 1000 + clock[0]), \
                    patch('vision.__main__.time.sleep'), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                main(['--model', 'fixture.task', '--video', 'fixture.avi', '--no-overlay',
                      '--no-hand-view', '--dry-run', '--relative', '--metrics-json', str(metrics_path),
                      '--calibration', str(Path(folder) / 'absent.json')])
            events = [json.loads(line) for line in output.getvalue().splitlines()]
            report = json.loads(metrics_path.read_text())
            self.assertEqual(len(events), 2)  # engage, then resumed movement; none in the gap
            self.assertEqual([event['seq'] for event in events], [0, 1])
            self.assertEqual(report['camera_diagnostics']['hand_absent_frames'], 2)
            self.assertEqual(report['camera_diagnostics']['presence_dropouts'], 1)


if __name__ == '__main__':
    unittest.main()
