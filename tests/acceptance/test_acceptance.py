"""Automated versions of the acceptance checks in docs/ARCHITECTURE.md.

These need no hardware. Engine control and disconnect checks use real loopback
sockets; manual hardware checks are in MANUAL.md.
"""
import sys
import asyncio
import json
import socket
import threading
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audio import Engine, EngineConfig  # noqa: E402
from audio.fileio import make_test_signal  # noqa: E402
from tools.latency.measure import find_onsets, summarize_ms, time_engine  # noqa: E402

SR = 48000
BLOCK = 128
CEILING = 10 ** (-1 / 20)


def run(engine, mono, block=BLOCK):
    out = np.zeros((len(mono), 2), np.float32)
    for s in range(0, len(mono), block):
        engine.process(mono[s:s + block], out[s:s + block])
    return out


class SustainedPlay(unittest.TestCase):
    def test_sixty_seconds_with_constant_control_traffic(self):
        """60 s of playing with gesture-rate parameter events and periodic pedal presses."""
        rng = np.random.default_rng(42)
        e = Engine(EngineConfig(samplerate=SR, input_gain_db=6))
        signal = np.tile(make_test_signal(seconds=6.0, samplerate=SR), 10)
        out = np.zeros((len(signal), 2), np.float32)
        blocks_per_sec = SR // BLOCK
        for i, s in enumerate(range(0, len(signal), BLOCK)):
            # ~30 Hz gesture updates for both controls, with occasional low-confidence noise
            if i % (blocks_per_sec // 30) == 0:
                e.submit({"type": "parameter", "control": "filter",
                          "value": float(rng.uniform()), "confidence": float(rng.uniform(0.3, 1.0))})
                e.submit({"type": "parameter", "control": "reverb",
                          "value": float(rng.uniform()), "confidence": 0.9})
            if i % (blocks_per_sec * 7) == 0:
                e.toggle_loop()
            if i % (blocks_per_sec * 11) == 0:
                e.toggle_bypass()
            e.process(signal[s:s + BLOCK], out[s:s + BLOCK])
        snap = e.snapshot()
        self.assertTrue(np.all(np.isfinite(out)))
        self.assertLessEqual(float(np.max(np.abs(out))), CEILING + 1e-6)
        self.assertEqual(snap["blocks"], -(-len(signal) // BLOCK))
        self.assertEqual(len(e._actions), 0, "action queue must not build a backlog")
        # The level at the end should be in the same range as the start (no runaway gain).
        first, last = out[SR:2 * SR, 0], out[-SR:, 0]
        ratio = np.sqrt(np.mean(last ** 2)) / max(np.sqrt(np.mean(first ** 2)), 1e-9)
        self.assertLess(ratio, 4.0)

    def test_engine_keeps_up_with_real_time(self):
        # Mean, not p99: tail latency on a shared laptop or CI runner reflects other
        # processes, not the engine. Real-time headroom on the audio host is measured
        # with tools/latency and the xrun counter in tests/acceptance/MANUAL.md.
        rows = time_engine(blocksizes=(128,), iterations=500)
        self.assertLess(rows[0]["mean_ms"], rows[0]["budget_ms"] * 0.5,
                        "mean block time should stay under half the real-time budget")


class LoopReliability(unittest.TestCase):
    def test_loop_start_stop_fifty_times(self):
        e = Engine(EngineConfig(samplerate=SR, max_loop_seconds=1.0))
        phrase = make_test_signal(seconds=0.3, samplerate=SR)
        for _ in range(50):
            e.toggle_loop()                     # record
            run(e, phrase)
            e.toggle_loop()                     # play
            run(e, np.zeros(SR // 10, np.float32))
            self.assertEqual(e.snapshot()["loop"]["state"], "playing")
            e.toggle_loop()                     # clear
            run(e, np.zeros(BLOCK, np.float32))
            self.assertEqual(e.snapshot()["loop"]["state"], "idle")
        silent = run(e, np.zeros(SR // 10, np.float32))
        self.assertLess(float(np.max(np.abs(silent[SR // 20:]))), 1e-3)


class UnsafeControlsCannotSweep(unittest.IsolatedAsyncioTestCase):
    def _filter_after(self, events):
        e = Engine(EngineConfig(samplerate=SR, min_confidence=0.6))
        for ev in events:
            e.submit(ev)
        run(e, np.zeros(SR // 4, np.float32))
        return e.snapshot()["filter"]["value"]

    def test_no_hand_means_no_change(self):
        self.assertEqual(self._filter_after([]), 1.0)

    def test_low_confidence_hand_is_ignored(self):
        events = [{"type": "parameter", "control": "filter", "value": 0.0, "confidence": c}
                  for c in (0.1, 0.3, 0.59)]
        self.assertEqual(self._filter_after(events), 1.0)

    def test_malformed_events_are_ignored(self):
        events = [{"type": "parameter", "control": "filter", "value": v, "confidence": 1.0}
                  for v in (-1, 2, float("inf"), "0")]
        self.assertEqual(self._filter_after(events), 1.0)

    def test_valid_change_is_smoothed_not_stepped(self):
        e = Engine(EngineConfig(samplerate=SR))
        e.set_filter(0.0)
        run(e, np.zeros(BLOCK, np.float32))
        self.assertGreater(e.snapshot()["filter"]["value"], 0.5)

    async def test_stale_and_duplicate_events_are_dropped(self):
        from engine import Runtime
        audio = Engine()
        runtime = Runtime(audio, udp_port=0, ws_port=None)
        await runtime.start()
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            for _ in range(100):
                if runtime.udp: break
                await asyncio.sleep(0.01)
            self.assertIsNotNone(runtime.udp)
            now = runtime.router.clock()
            base = dict(version=1, source='vision', seq=0, timestamp_ms=now,
                        type='parameter', control='filter', value=0.3, confidence=0.9)
            for event in [base, dict(base, value=0.9), dict(base, seq=1, value=0, timestamp_ms=now-1000)]:
                client.sendto(json.dumps(event).encode(), ('127.0.0.1', runtime.udp_port))
            for _ in range(100):
                if sum(runtime.router.counts.values()) == 3: break
                await asyncio.sleep(0.01)
            run(audio, np.zeros(BLOCK, np.float32))
            self.assertEqual(runtime.router.counts['accepted'], 1)
            self.assertEqual(runtime.router.counts['duplicate'], 1)
            self.assertEqual(runtime.router.counts['stale'], 1)
            self.assertEqual(audio.snapshot()['filter']['target'], 0.3)
        finally:
            client.close()
            await runtime.close()


class DisconnectKeepsAudio(unittest.IsolatedAsyncioTestCase):
    def test_manual_bypass_works_with_no_senders(self):
        e = Engine(EngineConfig(samplerate=SR))
        e.toggle_bypass()
        run(e, np.zeros(BLOCK * 8, np.float32))
        self.assertTrue(e.snapshot()["bypass"])

    async def test_killing_an_adapter_leaves_audio_running(self):
        from engine import Runtime
        audio = Engine()
        runtime = Runtime(audio, udp_port=0, ws_port=None)
        stop = threading.Event()
        signal = np.zeros(BLOCK, np.float32)
        output = np.zeros((BLOCK, 2), np.float32)
        def render():
            while not stop.wait(0.003): audio.process(signal, output)
        worker = threading.Thread(target=render)
        worker.start()
        await runtime.start()
        try:
            for _ in range(100):
                if runtime.udp: break
                await asyncio.sleep(0.01)
            self.assertIsNotNone(runtime.udp)
            runtime.tasks['udp'].cancel()
            await asyncio.gather(runtime.tasks['udp'], return_exceptions=True)
            before = audio.snapshot()['blocks']
            audio.toggle_bypass()
            await asyncio.sleep(0.05)
            self.assertGreater(audio.snapshot()['blocks'], before)
            self.assertTrue(audio.snapshot()['bypass'])
            self.assertEqual(runtime.adapters['udp']['status'], 'stopped')
        finally:
            stop.set(); worker.join(1)
            await runtime.close()


class LatencyDetection(unittest.TestCase):
    def test_finds_known_round_trip(self):
        rng = np.random.default_rng(1)
        clicks = [SR // 2 + i * SR // 2 for i in range(10)]
        delay = int(0.0123 * SR)  # 12.3 ms
        rec = rng.normal(0, 0.002, clicks[-1] + SR).astype(np.float32)
        for f in clicks:
            rec[f + delay:f + delay + 48] += 0.2
        summary = summarize_ms(find_onsets(rec, clicks, SR), SR)
        self.assertEqual(summary["detected"], 10)
        self.assertAlmostEqual(summary["median_ms"], 12.3, delta=0.1)

    def test_missing_returns_are_reported(self):
        clicks = [SR // 2, SR]
        rec = np.zeros(2 * SR, np.float32)
        rec[SR // 2 + 100] = 0.3  # only the first click comes back
        summary = summarize_ms(find_onsets(rec, clicks, SR), SR)
        self.assertEqual((summary["clicks"], summary["detected"]), (2, 1))


if __name__ == "__main__":
    unittest.main()
