"""Synthetic tests for thumb-to-pinky effect switching in BrowserVision."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import numpy as np

from audio import Engine, EngineConfig
from engine.runtime import Runtime
from tools.virtual_guitar.browser_vision import BrowserVision


class BrowserVisionSwitcherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.audio = Engine(EngineConfig(samplerate=16000))
        self.audio.set_filter(0.40)
        self.audio.set_reverb(0.15)
        self.runtime = Runtime(self.audio, udp_port=0, ws_port=0)
        await self.runtime.start()
        for _ in range(100):
            if self.runtime.udp is not None:
                break
            await asyncio.sleep(0.01)

        self.output = np.zeros((128, 2), np.float32)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.model_path = Path(self.temp_dir.name) / 'mock_model.task'
        self.model_path.write_text('mock model asset')

    def pump(self):
        self.audio.process(np.zeros(128, np.float32), self.output)

    async def asyncTearDown(self):
        self.temp_dir.cleanup()
        await self.runtime.close()

    async def test_thumb_to_pinky_hold_switches_filter_to_reverb_and_back(self):
        """Holding thumb-to-pinky switches active effect with independent relative pickup."""
        class MockDetector:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def detect_for_video(self, image, stamp):
                vals = image[0, 0, :]
                y = vals[0] / 100.0
                pinch = vals[1] / 100.0
                confidence = vals[2] / 100.0
                pinky_touch = vals[3] if len(vals) > 3 else 0
                ring_touch = vals[4] if len(vals) > 4 else 0
                if confidence == 0:
                    return NS(hand_landmarks=[], handedness=[])
                points = [NS(x=0.5, y=0.5) for _ in range(21)]
                # Palm center at landmark 9
                points[0] = NS(x=0.5, y=float(y) + 0.25)
                points[9] = NS(x=0.5, y=float(y))
                points[5] = NS(x=0.4, y=0.5)
                points[17] = NS(x=0.6, y=0.5)
                # Thumb tip at landmark 4: (0.5, 0.5)
                # Index tip at landmark 8
                points[8] = NS(x=0.5 + 0.2 * pinch, y=0.5)
                # Pinky & ring fingers
                if pinky_touch == 1:
                    # Thumb and pinky tips touching
                    points[20] = NS(x=0.5, y=0.5)
                    points[19] = NS(x=0.52, y=0.5)
                    points[16] = NS(x=0.65, y=0.5)
                elif ring_touch == 1:
                    # Thumb and ring tip touching (natural alternative)
                    points[16] = NS(x=0.5, y=0.5)
                    points[19] = points[20] = NS(x=0.75, y=0.5)
                else:
                    # Open outer fingers
                    points[16] = points[19] = points[20] = NS(x=0.75, y=0.5)
                return NS(hand_landmarks=[points], handedness=[[NS(score=float(confidence))]])

        def decode(data, mode):
            frame = np.zeros((480, 640, 5), np.uint8)
            frame[0, 0, :len(data)] = list(data)
            return frame

        cv = NS(imdecode=decode, cvtColor=lambda img, mode: img, IMREAD_COLOR=1, COLOR_BGR2RGB=1)
        mp = NS(Image=lambda image_format, data: data, ImageFormat=NS(SRGB=1), tasks=NS(
            BaseOptions=lambda **kw: kw,
            vision=NS(HandLandmarkerOptions=lambda **kw: kw, RunningMode=NS(VIDEO=1),
                      HandLandmarker=NS(create_from_options=lambda opt: MockDetector()))))

        with patch.dict('sys.modules', {'cv2': cv, 'mediapipe': mp}):
            camera = BrowserVision(
                self.model_path,
                udp_port=self.runtime.udp_port,
                hand_port=0,
                read_target=lambda ctrl: self.audio.snapshot()[ctrl]['target'],
                read_filter=lambda: self.audio.snapshot()['filter']['target'],
                gesture_switch_hold=0.20,
            )
            camera.start()
            for _ in range(100):
                if camera.status in ('waiting', 'error'):
                    break
                await asyncio.sleep(0.01)
            self.assertIsNone(camera.error)

            async def submit_frame(y, pinch, confidence=0.95, pinky=0, ring=0):
                cnt = camera.frame_count
                camera.submit(bytes([round(y * 100), round(pinch * 100), round(confidence * 100), pinky, ring]))
                for _ in range(100):
                    if camera.frame_count > cnt:
                        break
                    await asyncio.sleep(0.01)
                self.pump()

            try:
                # 1. Initial control is 'filter'
                self.assertEqual(camera.snapshot()['control'], 'filter')
                self.assertEqual(camera.snapshot()['switch_target'], 'reverb')
                self.assertFalse(camera.snapshot()['switching'])

                # Open hand to arm
                await submit_frame(0.5, 0.60)
                snap = camera.snapshot()
                self.assertTrue(snap['hand_present'])
                self.assertTrue(snap['hand_armed'])
                self.assertFalse(snap['hand_engaged'])

                # Pinch index at y=0.5 -> engages filter drag
                await submit_frame(0.5, 0.10)
                self.assertTrue(camera.snapshot()['hand_engaged'])

                # Drag up to y=0.3 -> raises filter
                await submit_frame(0.3, 0.10)
                filter_val = self.audio.snapshot()['filter']['target']
                self.assertGreater(filter_val, 0.40)
                reverb_val_before = self.audio.snapshot()['reverb']['target']
                self.assertEqual(reverb_val_before, 0.15)  # Reverb unchanged

                # Open hand -> holds filter value
                await submit_frame(0.3, 0.60)
                self.assertFalse(camera.snapshot()['hand_engaged'])
                self.assertAlmostEqual(self.audio.snapshot()['filter']['target'], filter_val)

                # 2. Brief touch (<0.20s) must NOT switch
                await submit_frame(0.5, 0.60, pinky=1)
                self.assertTrue(camera.snapshot()['switching'])
                self.assertEqual(camera.snapshot()['control'], 'filter')

                # Release contact before hold time
                await submit_frame(0.5, 0.60, pinky=0)
                self.assertFalse(camera.snapshot()['switching'])
                self.assertEqual(camera.snapshot()['control'], 'filter')

                # 3. Hold thumb-to-pinky for >= 0.20s -> switches to reverb!
                # Start dwell
                await submit_frame(0.5, 0.60, pinky=1)
                self.assertTrue(camera.snapshot()['switching'])
                # Hold for ~0.25s
                await asyncio.sleep(0.22)
                await submit_frame(0.5, 0.60, pinky=1)

                self.assertEqual(camera.snapshot()['control'], 'reverb')
                self.assertEqual(camera.snapshot()['switch_target'], 'filter')
                self.assertFalse(camera.snapshot()['switching'])

                # Release pinky contact
                await submit_frame(0.5, 0.60, pinky=0)

                # 4. Control reverb: arm open hand, then pinch and drag
                await submit_frame(0.4, 0.60)
                self.assertTrue(camera.snapshot()['hand_armed'])

                # Pinch at y=0.4 -> picks up engine reverb (0.15) without jump
                await submit_frame(0.4, 0.10)
                self.assertTrue(camera.snapshot()['hand_engaged'])

                # Drag up to y=0.2 -> increases reverb
                await submit_frame(0.2, 0.10)
                new_reverb = self.audio.snapshot()['reverb']['target']
                self.assertGreater(new_reverb, 0.15)
                # Filter remains at its held value
                self.assertAlmostEqual(self.audio.snapshot()['filter']['target'], filter_val)

                # Release index
                await submit_frame(0.2, 0.60)
                self.assertFalse(camera.snapshot()['hand_engaged'])

                # 5. Natural alternative outer-finger gesture: thumb to ring finger tip
                await submit_frame(0.5, 0.60, ring=1)
                self.assertTrue(camera.snapshot()['switching'])
                await asyncio.sleep(0.22)
                await submit_frame(0.5, 0.60, ring=1)

                # Switched back to filter!
                self.assertEqual(camera.snapshot()['control'], 'filter')
                self.assertEqual(camera.snapshot()['switch_target'], 'reverb')

                # Release ring contact
                await submit_frame(0.5, 0.60, ring=0)

                # 6. Re-engage filter: picks up filter_val without jump!
                await submit_frame(0.5, 0.60)
                await submit_frame(0.5, 0.10)
                # Target in engine should still equal filter_val
                self.assertAlmostEqual(self.audio.snapshot()['filter']['target'], filter_val, places=2)

                # 7. Manual set_control API works and syncs
                camera.set_control('reverb')
                self.assertEqual(camera.snapshot()['control'], 'reverb')
                camera.set_control('filter')
                self.assertEqual(camera.snapshot()['control'], 'filter')

            finally:
                camera.close()

    async def test_low_confidence_and_stale_hand_resets_dwell(self):
        """Switcher resets dwell timer on low confidence or missing hand."""
        class MockDetector:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def detect_for_video(self, image, stamp):
                vals = image[0, 0, :]
                y = vals[0] / 100.0
                pinch = vals[1] / 100.0
                confidence = vals[2] / 100.0
                pinky_touch = vals[3] if len(vals) > 3 else 0
                if confidence == 0:
                    return NS(hand_landmarks=[], handedness=[])
                points = [NS(x=0.5, y=0.5) for _ in range(21)]
                points[0] = NS(x=0.5, y=float(y) + 0.25)
                points[9] = NS(x=0.5, y=float(y))
                points[5] = NS(x=0.4, y=0.5)
                points[17] = NS(x=0.6, y=0.5)
                points[8] = NS(x=0.5 + 0.2 * pinch, y=0.5)
                points[20] = NS(x=0.5, y=0.5) if pinky_touch else NS(x=0.75, y=0.5)
                points[16] = points[19] = NS(x=0.75, y=0.5)
                return NS(hand_landmarks=[points], handedness=[[NS(score=float(confidence))]])

        def decode(data, mode):
            frame = np.zeros((480, 640, 4), np.uint8)
            frame[0, 0, :len(data)] = list(data)
            return frame

        cv = NS(imdecode=decode, cvtColor=lambda img, mode: img, IMREAD_COLOR=1, COLOR_BGR2RGB=1)
        mp = NS(Image=lambda image_format, data: data, ImageFormat=NS(SRGB=1), tasks=NS(
            BaseOptions=lambda **kw: kw,
            vision=NS(HandLandmarkerOptions=lambda **kw: kw, RunningMode=NS(VIDEO=1),
                      HandLandmarker=NS(create_from_options=lambda opt: MockDetector()))))

        with patch.dict('sys.modules', {'cv2': cv, 'mediapipe': mp}):
            camera = BrowserVision(
                self.model_path,
                udp_port=self.runtime.udp_port,
                hand_port=0,
                read_target=lambda ctrl: self.audio.snapshot()[ctrl]['target'],
                read_filter=lambda: self.audio.snapshot()['filter']['target'],
                gesture_switch_hold=0.20,
            )
            camera.start()
            for _ in range(100):
                if camera.status in ('waiting', 'error'):
                    break
                await asyncio.sleep(0.01)

            async def submit_frame(y, pinch, confidence=0.95, pinky=0):
                cnt = camera.frame_count
                camera.submit(bytes([round(y * 100), round(pinch * 100), round(confidence * 100), pinky]))
                for _ in range(100):
                    if camera.frame_count > cnt:
                        break
                    await asyncio.sleep(0.01)
                self.pump()

            try:
                # Start touch
                await submit_frame(0.5, 0.60, confidence=0.9, pinky=1)
                self.assertTrue(camera.snapshot()['switching'])

                # Low confidence frame (< 0.50) -> must reset dwell
                await submit_frame(0.5, 0.60, confidence=0.3, pinky=1)
                self.assertFalse(camera.snapshot()['switching'])
                self.assertEqual(camera.snapshot()['control'], 'filter')

                # Missing hand frame -> must reset dwell
                await submit_frame(0.5, 0.60, confidence=0.9, pinky=1)
                self.assertTrue(camera.snapshot()['switching'])
                await submit_frame(0.5, 0.60, confidence=0.0, pinky=1)
                self.assertFalse(camera.snapshot()['switching'])
                self.assertEqual(camera.snapshot()['control'], 'filter')
            finally:
                camera.close()
