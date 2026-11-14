"""Scripted, clearly simulated performance: loop pedal presses and pinch sweeps.

Pedal presses are sent as source "manual" (the real Arduino arrives over serial);
pinch sweeps are sent as source "vision" at 30 Hz with confidence 0.9.
If a HandState is passed, the simulated hand-view feed follows the same script.
"""
from __future__ import annotations

import asyncio
import math

from .events import Sender

CYCLE_S = 16.0
RATE_HZ = 30


async def sweep(sender: Sender, control: str, center: float, depth: float, seconds: float,
                period: float = 2.2, hand=None):
    steps = int(seconds * RATE_HZ)
    if hand is not None:
        hand.present, hand.engaged, hand.control = True, True, control
    try:
        for i in range(steps):
            t = i / RATE_HZ
            value = min(1.0, max(0.0, center + depth * math.sin(2 * math.pi * t / period)))
            sender.send(control, value, 0.9)
            if hand is not None:
                hand.value = value
            await asyncio.sleep(1 / RATE_HZ)
    finally:
        if hand is not None:
            hand.engaged = False


def _show(view, present: bool):
    if view is not None:
        view.present = present


async def run_demo(port: int, cycles: int | None = None, log=print, view=None):
    pedal, hand = Sender('manual', port=port), Sender('vision', port=port)
    try:
        n = 0
        while cycles is None or n < cycles:
            _show(view, False)
            log('[sim demo] pedal: record'); pedal.send('loop')
            await asyncio.sleep(2.5)
            _show(view, True)  # hand comes into frame, open, not driving anything
            await asyncio.sleep(1.5)
            log('[sim demo] pedal: play'); pedal.send('loop')
            await asyncio.sleep(2.0)
            log('[sim demo] pinch: reverb'); await sweep(hand, 'reverb', 0.5, 0.35, 3.0, hand=view)
            await asyncio.sleep(1.0)
            log('[sim demo] pinch: filter'); await sweep(hand, 'filter', 0.55, 0.4, 3.0, hand=view)
            await asyncio.sleep(1.0)
            _show(view, False)  # hand leaves
            await asyncio.sleep(1.0)
            log('[sim demo] pedal: clear'); pedal.send('loop')
            await asyncio.sleep(1.0)
            n += 1
    finally:
        pedal.close(); hand.close()
