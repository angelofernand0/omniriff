"""Browser webcam frames through Joey's merged gesture controller and hand feed.

The browser owns camera permission. JPEG frames are sent to a bounded, latest-only
worker; no pixels are saved or sent outside localhost. Nothing runs in audio's
callback. The signal path after detection uses the same Controller/SceneMorph and
validated UDP envelope as ``python -m vision``. The play room tracks the middle
finger's palm joint: unlike the wrist, it remains in frame when the user lowers
a still-visible hand toward the bottom edge of a laptop camera.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import queue
import socket
import threading
import time

from vision.control import Controller
from vision.hand_view import HandView
from vision.scenes import SCENES, SceneMorph
from vision.tracking import HandSelector
from vision.slider import FilterSlider
from vision.switcher import EffectSwitcher
from vision.metrics import FrameMetrics


class BrowserVision:
    MAX_FRAME = 250_000

    def __init__(
        self,
        model: Path,
        *,
        udp_port: int,
        hand_port: int,
        scene=None,
        read_filter=None,
        read_target=None,
        gesture_switch: bool = True,
        gesture_switch_hold: float = 0.20,
    ):
        self.model = Path(model).resolve()
        self.udp_port, self.hand_port = udp_port, hand_port
        self.scene_name = scene
        self.read_filter = read_filter
        if read_target is not None:
            self.read_target = read_target
        elif read_filter is not None:
            def _fallback_read_target(ctrl='filter'):
                try:
                    return read_filter(ctrl)
                except TypeError:
                    return read_filter()
            self.read_target = _fallback_read_target
        else:
            self.read_target = None
        self.gesture_switch = gesture_switch
        self.gesture_switch_hold = gesture_switch_hold
        self.frames = queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.thread = None
        self.hand_view = None
        self.status = 'off'
        self.error = None
        self.frame_count = self.event_count = 0
        self.last_frame_at = 0.0
        self.hand_present = self.hand_confident = self.hand_engaged = self.hand_armed = False
        self.active_control = 'filter'
        self.switching = False
        self.last_switched_at = 0.0
        self.switcher = None
        self.metrics = FrameMetrics()

    def start(self):
        if self.thread is not None and self.thread.is_alive():
            return
        if not self.model.is_file():
            raise ValueError(f'Hand model missing: {self.model}. See vision/README.md setup.')
        self.stop_event.clear()
        self.frames = queue.Queue(maxsize=1)
        self.status, self.error = 'starting', None
        self.frame_count = self.event_count = 0
        self.hand_present = self.hand_confident = self.hand_engaged = self.hand_armed = False
        self.active_control = 'filter'
        self.switching = False
        self.last_switched_at = 0.0
        self.switcher = None
        self.metrics = FrameMetrics()
        self.thread = threading.Thread(target=self._run, name='browser-vision', daemon=True)
        self.thread.start()

    def submit(self, data: bytes):
        if self.status not in ('starting', 'running', 'waiting'):
            raise ValueError('Camera tracker is not running')
        if not 0 < len(data) <= self.MAX_FRAME:
            raise ValueError('Camera frame must be 1..250000 bytes')
        try:
            self.frames.get_nowait()
        except queue.Empty:
            pass
        try:
            self.frames.put_nowait(data)
        except queue.Full:
            pass

    def stop(self):
        self.stop_event.set()
        self.hand_present = self.hand_confident = self.hand_engaged = self.hand_armed = False
        self.switching = False
        self.status = 'stopping' if self.thread is not None and self.thread.is_alive() else 'off'

    def close(self):
        self.stop()
        if self.thread is not None:
            self.thread.join(timeout=2)

    def set_control(self, control: str):
        if control in ('filter', 'reverb'):
            self.active_control = control
            self.last_switched_at = time.monotonic()
            if self.switcher:
                self.switcher.set_control(control)

    def snapshot(self):
        control = self.scene_name if self.scene_name is not None else self.active_control
        target = 'reverb' if self.active_control == 'filter' else 'filter'
        return dict(status=self.status, error=self.error, frames=self.frame_count,
                    events=self.event_count, model_ready=self.model.is_file(),
                    hand_present=self.hand_present, hand_confident=self.hand_confident,
                    hand_engaged=self.hand_engaged,
                    hand_armed=self.hand_armed,
                    scene=self.scene_name, control=control,
                    switching=self.switching, switch_target=target,
                    last_switched_at=self.last_switched_at,
                    metrics=self.metrics.snapshot())

    def _run(self):
        try:
            self._track()
        except Exception as exc:
            self.error = f'{type(exc).__name__}: {exc}'[:240]
            self.status = 'error'
        else:
            self.status = 'off'

    def _track(self):
        import cv2
        import mediapipe as mp
        import numpy as np

        hand_view = self.hand_view = HandView(self.hand_port).start()
        try:
            if not hand_view.ready.wait(2) or hand_view.error:
                raise RuntimeError(f'Hand-view port unavailable: {hand_view.error or self.hand_port}')
            scene = SceneMorph(SCENES[self.scene_name]) if self.scene_name else None
            reader = self.read_target or self.read_filter
            if scene is None and reader is None:
                raise ValueError('Slider mode requires the current engine target')
            slider = FilterSlider(reader, control=self.active_control) if scene is None else None
            controller = slider.controller if slider else Controller(rate=10)
            switcher = self.switcher = EffectSwitcher(
                controls=['filter', 'reverb'],
                touch_threshold=0.38,
                release_threshold=0.52,
                hold_seconds=self.gesture_switch_hold,
                min_confidence=0.50,
            ) if (scene is None and self.gesture_switch) else None
            if switcher:
                switcher.set_control(self.active_control)
            selector = HandSelector()
            options = mp.tasks.vision.HandLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(self.model)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=2,
                min_hand_detection_confidence=0.6, min_hand_presence_confidence=0.6,
                min_tracking_confidence=0.6)
            stamp = -1
            started = time.monotonic()
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, mp.tasks.vision.HandLandmarker.create_from_options(options) as detector:
                self.status = 'waiting'
                while not self.stop_event.is_set():
                    try:
                        data = self.frames.get(timeout=0.2)
                    except queue.Empty:
                        if self.last_frame_at and time.monotonic() - self.last_frame_at > 0.7:
                            controller.update(None, None, 0., time.monotonic(), int(time.time() * 1000))
                            if switcher:
                                switcher.reset_dwell()
                            hand_view.publish(self._hand_frame(None, controller, 0., [], int(time.time() * 1000), scene, self.active_control))
                            self.hand_present = self.hand_confident = self.hand_engaged = self.hand_armed = False
                            self.switching = False
                            self.status = 'waiting'
                            self.last_frame_at = 0.0
                        continue
                    now = time.monotonic()
                    self.last_frame_at = now
                    frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is None or frame.ndim != 3 or frame.shape[0] > 1080 or frame.shape[1] > 1920:
                        continue
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    stamp = max(stamp + 1, int((now - started) * 1000))
                    result = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), stamp)
                    # MediaPipe can extrapolate the wrist below the image while
                    # the palm remains plainly visible. HandSelector correctly
                    # rejects out-of-frame centers, so select by an in-frame
                    # palm joint and use that same joint for the drag coordinate.
                    selected = selector.select([(hand[9].x, hand[9].y) for hand in result.hand_landmarks])
                    y = pinch = pinky_pinch = None
                    confidence = 0.
                    points = []
                    if selected is not None:
                        points = result.hand_landmarks[selected]
                        height, width = frame.shape[:2]
                        distance = lambda a, b: math.hypot((points[a].x-points[b].x)*width, (points[a].y-points[b].y)*height)
                        scale = distance(5, 17)
                        if scale > 1:
                            y = points[9].y
                            pinch = distance(4, 8) / scale
                            if switcher:
                                # Multi-landmark outer-finger distance:
                                # Minimum distance from thumb (tip 4 or IP 3)
                                # to pinky (tip 20, DIP 19) or ring tip (16).
                                # Ensures effortless recognition across webcam angles and hand sizes.
                                d_4_20 = distance(4, 20)
                                d_4_19 = distance(4, 19)
                                d_3_20 = distance(3, 20)
                                d_4_16 = distance(4, 16)
                                pinky_pinch = min(d_4_20, d_4_19, d_3_20, d_4_16) / scale
                            confidence = result.handedness[selected][0].score
                    wall_ms = int(time.time() * 1000)

                    # Freshness and suppression:
                    # Switcher dwell is reset on missing hand, stale frame, low confidence, or when actively dragging
                    fresh_frame = (time.monotonic() - now <= 0.25)
                    suppressed = (not fresh_frame) or (y is None) or (confidence < controller.confidence) or controller.active

                    if switcher:
                        switched = switcher.update(pinky_pinch, confidence, now, controller=controller, suppressed=suppressed)
                        if switched:
                            self.active_control = switcher.current_control
                            self.last_switched_at = now
                        self.switching = (switcher.touch_start is not None)

                    if self.active_control != controller.control:
                        if switcher:
                            switcher.set_control(self.active_control)
                        controller.control = self.active_control
                        controller.rearm()

                    gesture = (slider or controller).update(y, pinch, confidence, now, wall_ms)
                    self.hand_present = y is not None
                    self.hand_confident = self.hand_present and confidence >= controller.confidence
                    self.hand_engaged = self.hand_present and controller.active
                    self.hand_armed = self.hand_present and controller.armed
                    if slider:
                        self.error = slider.error
                    landmarks = [[min(1., max(0., p.x)), min(1., max(0., p.y))] for p in points] if y is not None else []
                    hand_view.publish(self._hand_frame(y, controller, confidence, landmarks, wall_ms, scene, self.active_control))
                    emitted = 0
                    for event in (scene.events(gesture) if scene else [gesture]) if gesture else []:
                        sock.sendto(json.dumps(event, allow_nan=False, separators=(',', ':')).encode(), ('127.0.0.1', self.udp_port))
                        self.event_count += 1
                        emitted += 1
                    self.metrics.record(now, time.monotonic(), emitted, hand_present=y is not None)
                    self.frame_count += 1
                    self.status = 'running'
        finally:
            hand_view.close()
            self.hand_view = None

    @staticmethod
    def _hand_frame(y, controller, confidence, landmarks, wall_ms, scene=None, control=None):
        ctrl = None if scene else (control or getattr(controller, 'control', 'filter'))
        return dict(version=1, type='hand', timestamp_ms=wall_ms,
                    present=y is not None, engaged=controller.active,
                    confidence=confidence, control=ctrl, value=controller.value,
                    landmarks=landmarks)

