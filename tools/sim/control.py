"""Manual test control for the simulator (SIMULATED input only).

The dashboard's `?manual=1` flag talks to these endpoints on the simulator's own web server
(`/sim/...`). With it you can stop everything the simulator does by itself (the scripted pedal
presses and pinch sweeps), mute the synthetic guitar, put a hand in frame and drive a pinch by
hand, so every change on screen is one you caused.

  /sim/state                          what is running
  /sim/auto?on=0|1                    the scripted demo (pedal presses, pinch sweeps, hand view)
  /sim/guitar?on=0|1                  the synthetic guitar
  /sim/hand?present=0|1[&engaged=0|1&control=filter|reverb&value=0..1]
                                      the simulated hand; engaged + value also send a pinch (source vision, 0.9)
  /sim/pedal                          one loop press (source manual), same as the L key
"""
from __future__ import annotations

import asyncio

from .demo import run_demo
from .events import Sender


class SimControl:
    def __init__(self, loop: asyncio.AbstractEventLoop, udp_port: int, view, guitar, guitar_level: float, demo_on: bool):
        self.loop, self.udp_port, self.view, self.guitar = loop, udp_port, view, guitar
        self.level = guitar_level or 0.28
        self.demo = None
        self.pedal = Sender('manual', port=udp_port)
        self.vision = Sender('vision', port=udp_port)
        if demo_on:
            self._start_demo()

    # runs on the event loop thread
    def _start_demo(self):
        if self.demo is None or self.demo.done():
            self.demo = asyncio.ensure_future(run_demo(self.udp_port, view=self.view))

    def _stop_demo(self):
        if self.demo is not None:
            self.demo.cancel()
            self.demo = None
        if self.view is not None:
            self.view.present = self.view.engaged = False

    def state(self) -> dict:
        v = self.view
        return {'auto': self.demo is not None and not self.demo.done(), 'guitar': self.guitar.level > 0,
                'hand': {'present': bool(v and v.present), 'engaged': bool(v and v.engaged)}}

    # runs on the http thread
    def handle(self, path: str, q: dict) -> dict:
        on = q.get('on') == '1'
        if path == '/sim/auto':
            self.loop.call_soon_threadsafe(self._start_demo if on else self._stop_demo)
        elif path == '/sim/guitar':
            self.guitar.level = self.level if on else 0.0
        elif path == '/sim/hand' and self.view is not None:
            self.view.present = q.get('present') == '1'
            self.view.engaged = self.view.present and q.get('engaged') == '1'
            control = q.get('control')
            if control in ('filter', 'reverb'):
                self.view.control = control
            try:
                value = min(1.0, max(0.0, float(q['value'])))
            except (KeyError, ValueError):
                value = None
            if self.view.engaged and value is not None and control in ('filter', 'reverb'):
                self.view.value = value
                self.vision.send(control, value, 0.9)
        elif path == '/sim/pedal':
            self.pedal.send('loop')
        elif path != '/sim/state':
            return {'error': 'unknown'}
        return self.state() if path != '/sim/auto' else {**self.state(), 'auto': on}
