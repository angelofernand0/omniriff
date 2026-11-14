"""Simulated hand-view feed (protocol/hand.schema.json) for building the dashboard without a camera.

A synthetic 21-point hand, laid out like MediaPipe's Hand Landmarker, served on the same
loopback WebSocket port vision/ uses (47802). Everything here is SIMULATED: it is not a
tracked hand and says nothing about vision accuracy.
"""
from __future__ import annotations

import asyncio
import json
import math
import time

# Open right hand, palm facing the camera, in hand units: wrist at the origin, fingers toward -y.
# Index order follows MediaPipe: 0 wrist; 1-4 thumb; 5-8 index; 9-12 middle; 13-16 ring; 17-20 pinky.
_OPEN = [
    (0.00, 0.00),
    (-0.32, -0.12), (-0.52, -0.30), (-0.66, -0.48), (-0.78, -0.62),
    (-0.22, -0.78), (-0.27, -1.10), (-0.30, -1.30), (-0.32, -1.48),
    (-0.02, -0.82), (-0.02, -1.18), (-0.02, -1.40), (-0.02, -1.60),
    (0.17, -0.77), (0.20, -1.08), (0.22, -1.28), (0.24, -1.44),
    (0.33, -0.66), (0.40, -0.90), (0.44, -1.05), (0.47, -1.18),
]
_PINCH_POINT = (-0.45, -0.95)  # where thumb tip and index tip meet when pinched
SCALE = 0.20                   # hand size in normalized image height, about arm length from the camera
ASPECT = 4 / 3                 # camera width / height; x is scaled so the hand isn't stretched


def hand_points(x: float, y: float, pinch: float, wobble: float = 0.0) -> list[list[float]]:
    """21 normalized [x, y] points with the wrist at (x, y). pinch in [0, 1] closes thumb and index tips."""
    pts = []
    for i, (hx, hy) in enumerate(_OPEN):
        if i in (3, 4, 7, 8):
            k = pinch * (1.0 if i in (4, 8) else 0.6)
            hx, hy = hx + (_PINCH_POINT[0] - hx) * k, hy + (_PINCH_POINT[1] - hy) * k
        if i > 0:
            hy += 0.03 * math.sin(wobble + i)  # small finger drift so it looks alive
        px = x + hx * SCALE / ASPECT
        py = y + hy * SCALE
        pts.append([round(min(1.0, max(0.0, px)), 4), round(min(1.0, max(0.0, py)), 4)])
    return pts


def pinch_ratio(pts: list[list[float]], width: int = 640, height: int = 480) -> float:
    """Same measure vision/ uses: thumb-index tip distance over palm width (5-17), in pixels."""
    d = lambda a, b: math.hypot((pts[a][0] - pts[b][0]) * width, (pts[a][1] - pts[b][1]) * height)
    return d(4, 8) / d(5, 17)


class HandState:
    """What the fake hand is doing. The demo script updates it; the feed publishes it."""

    def __init__(self):
        self.present = False
        self.engaged = False
        self.control: str | None = 'filter'
        self.value: float | None = None

    def frame(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        base = {'version': 1, 'type': 'hand', 'timestamp_ms': int(now * 1000),
                'control': self.control, 'value': self.value}
        if not self.present:
            return {**base, 'present': False, 'engaged': False, 'confidence': 0.0, 'landmarks': []}
        v = 0.5 if self.value is None else self.value
        # higher value = wrist higher, as with vision's calibration (kept in frame so fingertips aren't clipped)
        y = 0.85 - 0.4 * v if self.engaged else 0.7 + 0.02 * math.sin(now * 1.3)
        x = 0.55 + 0.03 * math.sin(now * 0.7)
        pts = hand_points(x, y, 1.0 if self.engaged else 0.0, wobble=now * 2.0)
        return {**base, 'present': True, 'engaged': self.engaged, 'confidence': 0.93, 'landmarks': pts}


async def serve_hand(state: HandState, port: int = 47802, rate_hz: float = 20.0, ready=None):
    """Serve state.frame() at rate_hz to every client on ws://127.0.0.1:port. Runs until cancelled."""
    from websockets.asyncio.server import serve

    async def client(ws):
        try:
            while True:
                await asyncio.wait_for(ws.send(json.dumps(state.frame(), separators=(',', ':'))), 0.1)
                await asyncio.sleep(1 / rate_hz)
        except Exception:
            return  # slow or gone viewer; never affects the sim

    async with serve(client, '127.0.0.1', port, max_size=4096) as server:
        if ready is not None:
            ready(server.sockets[0].getsockname()[1])
        await asyncio.Future()
