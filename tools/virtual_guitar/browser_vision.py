"""Browser webcam frames through Joey's merged gesture controller and hand feed.

The browser owns camera permission. JPEG frames are sent to a bounded, latest-only
worker; no pixels are saved or sent outside localhost. Nothing runs in audio's
callback. The signal path after detection is the same Controller/SceneMorph and
validated UDP envelope used by ``python -m vision``.
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
from vision.metrics import FrameMetrics


class BrowserVision:
    MAX_FRAME = 250_000

    def __init__(self, model: Path, *, udp_port: int, hand_port: int, scene=None, read_filter=None):
        self.model = Path(model).resolve()
        self.udp_port, self.hand_port = udp_port, hand_port
        self.scene_name = scene
        self.read_filter = read_filter
        self.frames = queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.thread = None
        self.hand_view = None
        self.status = 'off'
        self.error = None
        self.frame_count = self.event_count = 0
        self.last_frame_at = 0.0
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
        self.status = 'stopping' if self.thread is not None and self.thread.is_alive() else 'off'

    def close(self):
        self.stop()
        if self.thread is not None:
            self.thread.join(timeout=2)

    def snapshot(self):
        return dict(status=self.status, error=self.error, frames=self.frame_count,
                    events=self.event_count, model_ready=self.model.is_file(),
                    scene=self.scene_name, control='filter' if self.scene_name is None else 'scene',
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
            if scene is None and self.read_filter is None:
                raise ValueError('Slider mode requires the current engine filter target')
            slider = FilterSlider(self.read_filter) if scene is None else None
            controller = slider.controller if slider else Controller(rate=10)
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
                            hand_view.publish(self._hand_frame(None, controller, 0., [], int(time.time() * 1000), scene))
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
                    selected = selector.select([(hand[0].x, hand[0].y) for hand in result.hand_landmarks])
                    y = pinch = None
                    confidence = 0.
                    points = []
                    if selected is not None:
                        points = result.hand_landmarks[selected]
                        height, width = frame.shape[:2]
                        distance = lambda a, b: math.hypot((points[a].x-points[b].x)*width, (points[a].y-points[b].y)*height)
                        scale = distance(5, 17)
                        if scale > 1:
                            y = points[0].y
                            pinch = distance(4, 8) / scale
                            confidence = result.handedness[selected][0].score
                    wall_ms = int(time.time() * 1000)
                    gesture = (slider or controller).update(y, pinch, confidence, now, wall_ms)
                    if slider:
                        self.error = slider.error
                    landmarks = [[min(1., max(0., p.x)), min(1., max(0., p.y))] for p in points] if y is not None else []
                    hand_view.publish(self._hand_frame(y, controller, confidence, landmarks, wall_ms, scene))
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
    def _hand_frame(y, controller, confidence, landmarks, wall_ms, scene=None):
        return dict(version=1, type='hand', timestamp_ms=wall_ms,
                    present=y is not None, engaged=controller.active,
                    confidence=confidence, control=None if scene else 'filter', value=controller.value,
                    landmarks=landmarks)
