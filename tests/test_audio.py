import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio import Engine, EngineConfig  # noqa: E402
from audio.dsp import filter_cutoff_hz  # noqa: E402
from audio.fileio import make_test_signal, read_wav, write_wav  # noqa: E402
from audio.offline import render  # noqa: E402

SR = 48000
BLOCK = 128


def sine(freq, seconds, amp=0.5):
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def run(engine, mono, block=BLOCK, channels=2):
    out = np.zeros((len(mono), channels), np.float32)
    for s in range(0, len(mono), block):
        engine.process(mono[s:s + block], out[s:s + block])
    return out


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


class FilterTests(unittest.TestCase):
    def test_cutoff_mapping_is_bounded_and_monotonic(self):
        values = [filter_cutoff_hz(v, 120, 18000, SR) for v in np.linspace(0, 1, 21)]
        self.assertAlmostEqual(values[0], 120)
        self.assertAlmostEqual(values[-1], 18000)
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))
        self.assertEqual(filter_cutoff_hz(-5, 120, 18000, SR), 120)
        self.assertLessEqual(filter_cutoff_hz(1, 120, 30000, SR), 0.45 * SR)

    def test_closed_filter_attenuates_highs(self):
        tone = sine(6000, 0.5)
        open_e = Engine(EngineConfig(samplerate=SR))
        closed_e = Engine(EngineConfig(samplerate=SR))
        closed_e.set_filter(0.0)
        settle = int(0.25 * SR)
        open_rms = rms(run(open_e, tone)[settle:, 0])
        closed_rms = rms(run(closed_e, tone)[settle:, 0])
        self.assertGreater(open_rms, 0.3)
        self.assertLess(closed_rms, open_rms * 0.01)  # at least 40 dB down

    def test_filter_moves_smoothly(self):
        e = Engine(EngineConfig(samplerate=SR, smoothing_ms=40))
        run(e, np.zeros(BLOCK, np.float32))
        e.set_filter(0.0)
        run(e, np.zeros(BLOCK, np.float32))
        after_one_block = e.snapshot()["filter"]["value"]
        self.assertGreater(after_one_block, 0.5, "should not jump to the target in one block")
        run(e, np.zeros(SR // 2, np.float32))
        self.assertAlmostEqual(e.snapshot()["filter"]["value"], 0.0, places=4)


class ControlTests(unittest.TestCase):
    def test_rejects_invalid_and_low_confidence_events(self):
        e = Engine(EngineConfig(samplerate=SR, min_confidence=0.6))
        bad = [
            None,
            {"type": "parameter", "control": "filter", "value": 1.2, "confidence": 1},
            {"type": "parameter", "control": "filter", "value": float("nan"), "confidence": 1},
            {"type": "parameter", "control": "filter", "value": True, "confidence": 1},
            {"type": "parameter", "control": "filter", "value": 0.5},
            {"type": "parameter", "control": "loop", "value": 0.5, "confidence": 1},
            {"type": "action", "control": "filter"},
            {"type": "action", "control": "loop", "value": 1},
        ]
        for event in bad:
            with self.subTest(event=event):
                self.assertFalse(e.submit(event))
        self.assertFalse(e.submit({"type": "parameter", "control": "filter", "value": 0.2, "confidence": 0.3}))
        self.assertEqual(e.snapshot()["filter"]["target"], 1.0)
        self.assertTrue(e.submit({"type": "parameter", "control": "reverb", "value": 0.4, "confidence": 0.9}))
        events = e.snapshot()["events"]
        self.assertEqual(events, {"accepted": 1, "rejected": len(bad), "low_confidence": 1})

    def test_accepts_full_v1_envelope(self):
        e = Engine(EngineConfig(samplerate=SR))
        self.assertTrue(e.submit({"version": 1, "source": "vision", "seq": 3, "timestamp_ms": 1,
                                  "type": "parameter", "control": "filter", "value": 0.4, "confidence": 0.95}))
        self.assertEqual(e.snapshot()["filter"]["target"], 0.4)


class ActionQueueTests(unittest.TestCase):
    def test_full_queue_rejects_instead_of_overwriting(self):
        from audio.engine import ACTION_QUEUE_LIMIT
        e = Engine(EngineConfig(samplerate=SR))
        results = [e.toggle_bypass() for _ in range(ACTION_QUEUE_LIMIT + 1)]
        self.assertEqual(results.count(True), ACTION_QUEUE_LIMIT)
        self.assertFalse(results[-1], "the action past the limit must be rejected, not silently dropped")
        run(e, np.zeros(BLOCK * 8, np.float32))  # drains 8 per block
        # Exactly the accepted toggles were applied: an even count leaves bypass off.
        self.assertEqual(e.snapshot()["bypass"], ACTION_QUEUE_LIMIT % 2 == 1)
        self.assertEqual(e.snapshot()["events"]["rejected"], 1)

    def test_queue_accepts_again_after_draining(self):
        from audio.engine import ACTION_QUEUE_LIMIT
        e = Engine(EngineConfig(samplerate=SR))
        for _ in range(ACTION_QUEUE_LIMIT):
            e.toggle_loop()
        self.assertFalse(e.toggle_bypass())
        run(e, np.zeros(BLOCK, np.float32))
        self.assertTrue(e.toggle_bypass())

    def test_concurrent_submitters_never_exceed_the_limit(self):
        import threading
        from audio.engine import ACTION_QUEUE_LIMIT
        e = Engine(EngineConfig(samplerate=SR))
        accepted = []

        def spam():
            accepted.append(sum(e.toggle_bypass() for _ in range(50)))

        threads = [threading.Thread(target=spam) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(accepted), ACTION_QUEUE_LIMIT)
        self.assertLessEqual(len(e._actions), ACTION_QUEUE_LIMIT)


class BypassTests(unittest.TestCase):
    def test_bypass_is_dry_and_click_free(self):
        e = Engine(EngineConfig(samplerate=SR))
        e.set_filter(0.0)
        tone = sine(3000, 0.6)
        run(e, tone[: SR // 4])
        e.toggle_bypass()
        out = run(e, tone[SR // 4:])[:, 0]
        self.assertTrue(e.snapshot()["bypass"])
        tail = slice(SR // 10, None)
        np.testing.assert_allclose(out[tail], tone[SR // 4:][tail], atol=1e-5)
        jumps = np.max(np.abs(np.diff(out)))
        max_sine_step = 2 * np.pi * 3000 / SR * 0.5
        self.assertLess(jumps, max_sine_step * 1.5)

    def test_bypass_toggles_back(self):
        e = Engine(EngineConfig(samplerate=SR))
        e.toggle_bypass()
        e.toggle_bypass()
        run(e, np.zeros(BLOCK, np.float32))
        self.assertFalse(e.snapshot()["bypass"])


class LoopTests(unittest.TestCase):
    def test_record_play_clear(self):
        e = Engine(EngineConfig(samplerate=SR))
        phrase = sine(440, 0.5)
        e.toggle_loop()
        run(e, phrase)
        self.assertEqual(e.snapshot()["loop"]["state"], "recording")
        e.toggle_loop()
        out = run(e, np.zeros(len(phrase) * 2, np.float32))[:, 0]
        snap = e.snapshot()["loop"]
        self.assertEqual(snap["state"], "playing")
        self.assertAlmostEqual(snap["seconds"], 0.5, places=2)
        mid = slice(len(phrase) // 4, 3 * len(phrase) // 4)
        np.testing.assert_allclose(out[mid], phrase[mid], atol=0.02)  # filter fully open: near-identity
        np.testing.assert_allclose(out[len(phrase):][mid], phrase[mid], atol=0.02)  # repeats
        e.toggle_loop()
        silent = run(e, np.zeros(SR // 10, np.float32))
        self.assertEqual(e.snapshot()["loop"]["state"], "idle")
        self.assertLess(np.max(np.abs(silent[BLOCK * 4:])), 1e-3)

    def test_loop_stops_recording_at_max_length(self):
        e = Engine(EngineConfig(samplerate=SR, max_loop_seconds=0.1))
        e.toggle_loop()
        run(e, sine(220, 0.3))
        self.assertEqual(e.snapshot()["loop"]["state"], "playing")
        self.assertAlmostEqual(e.snapshot()["loop"]["seconds"], 0.1, places=3)


class OutputSafetyTests(unittest.TestCase):
    def test_limiter_caps_output_without_hard_clipping(self):
        ceiling = 10 ** (-1 / 20)
        e = Engine(EngineConfig(samplerate=SR, input_gain_db=12, output_ceiling_db=-1))
        out = run(e, sine(200, 0.5, amp=0.9))[:, 0]
        self.assertLessEqual(float(np.max(np.abs(out))), ceiling + 1e-6)
        self.assertEqual(e.snapshot()["clipped_samples"], 0, "limiter, not the hard clip, should catch it")
        # A hard-clipped sine sits flat at the ceiling most of the time; a limited one doesn't.
        settled = out[SR // 10:]
        self.assertLess(float(np.mean(np.abs(settled) >= ceiling * 0.99)), 0.1)

    def test_limiter_leaves_quiet_signal_untouched(self):
        e = Engine(EngineConfig(samplerate=SR))
        tone = sine(440, 0.3, amp=0.3)
        out = run(e, tone)[:, 0]
        ref = Engine(EngineConfig(samplerate=SR, output_ceiling_db=6))  # limiter far above the signal
        np.testing.assert_allclose(out, run(ref, tone)[:, 0], atol=1e-6)

    def test_limiter_recovers_after_a_burst(self):
        e = Engine(EngineConfig(samplerate=SR, input_gain_db=12, limiter_release_ms=150))
        run(e, sine(200, 0.2, amp=0.9))          # loud: heavy gain reduction
        quiet = sine(200, 1.0, amp=0.05)
        out = run(e, quiet)[:, 0]
        loud_gain = 10 ** (12 / 20)
        tail_ratio = np.max(np.abs(out[-SR // 10:])) / (0.05 * loud_gain)
        self.assertGreater(tail_ratio, 0.95, "gain should return to unity within 1 s")

    def test_loop_plus_reverb_stack_does_not_clip(self):
        e = Engine(EngineConfig(samplerate=SR, input_gain_db=6))
        e.set_reverb(0.8)
        sig = make_test_signal(seconds=4.0, samplerate=SR)
        e.toggle_loop()
        run(e, sig[: 2 * SR])
        e.toggle_loop()
        out = run(e, sig[2 * SR:])
        self.assertEqual(e.snapshot()["clipped_samples"], 0)
        self.assertLessEqual(float(np.max(np.abs(out))), 10 ** (-1 / 20) + 1e-6)

    def test_large_and_odd_blocks(self):
        e = Engine(EngineConfig(samplerate=SR, max_block=256))
        tone = sine(500, 0.1)
        out = np.zeros((len(tone), 1), np.float32)
        e.process(tone, out)  # larger than max_block, odd length
        self.assertTrue(np.all(np.isfinite(out)))
        self.assertGreater(rms(out), 0.3)

    def test_snapshot_keys_are_stable(self):
        snap = Engine().snapshot()
        self.assertEqual(
            set(snap),
            {"samplerate", "bypass", "loop", "filter", "reverb", "input_peak_dbfs", "output_peak_dbfs",
             "xruns", "clipped_samples", "blocks", "events"},
        )


class FileModeTests(unittest.TestCase):
    def test_wav_roundtrip_and_offline_render(self):
        signal = make_test_signal(seconds=1.0, samplerate=SR)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "in.wav"
            write_wav(path, signal, SR)
            data, sr = read_wav(path)
        self.assertEqual(sr, SR)
        np.testing.assert_allclose(data[:, 0], signal, atol=1 / 32767 + 1e-6)
        e = Engine(EngineConfig(samplerate=SR))
        out = render(e, data[:, 0], sweep_period=0.5, loop_times=(0.1, 0.4))
        self.assertEqual(out.shape, (len(signal), 2))
        self.assertTrue(np.all(np.isfinite(out)))
        self.assertEqual(e.snapshot()["loop"]["state"], "playing")


def set_reverb(engine, value):
    return engine.submit({"type": "parameter", "control": "reverb", "value": value, "confidence": 1.0})


class ReverbTests(unittest.TestCase):
    def _impulse_response(self, value, seconds=3.5):
        e = Engine(EngineConfig(samplerate=SR))
        set_reverb(e, value)
        run(e, np.zeros(SR // 2, np.float32))  # let the amount settle
        x = np.zeros(int(seconds * SR), np.float32)
        x[0] = 0.5
        return run(e, x)[:, 0]

    def test_reverb_adds_a_decaying_tail(self):
        y = self._impulse_response(1.0)

        def energy(t):
            seg = y[int(t * SR):int(t * SR) + 2400]
            return float(np.mean(np.square(seg)))

        self.assertGreater(energy(0.5), 1e-8, "tail should still be audible at 0.5 s")
        self.assertLess(energy(3.0), energy(0.5) * 1e-4, "tail should decay by >40 dB")
        self.assertTrue(np.all(np.isfinite(y)))

    def test_zero_reverb_adds_nothing(self):
        y = self._impulse_response(0.0, seconds=0.5)
        self.assertLess(float(np.max(np.abs(y[BLOCK * 2:]))), 1e-4)

    def test_reverb_stays_bounded_on_loud_input(self):
        e = Engine(EngineConfig(samplerate=SR, input_gain_db=6))
        set_reverb(e, 1.0)
        out = run(e, make_test_signal(seconds=2.0, samplerate=SR))
        self.assertTrue(np.all(np.isfinite(out)))
        self.assertLessEqual(float(np.max(np.abs(out))), 10 ** (-1 / 20) + 1e-6)
        self.assertTrue(e.snapshot()["reverb"]["dsp"])

    def test_subblock_longer_than_reverb_delay_is_rejected(self):
        with self.assertRaises(ValueError):
            Engine(EngineConfig(samplerate=SR, subblock=1024))


class LevelCheckTests(unittest.TestCase):
    def test_advice_bands(self):
        from audio.levels import analyze_levels
        cases = {
            "silent": np.zeros(SR, np.float32),
            "turn_up": sine(196, 1.0, amp=0.02),     # about -34 dBFS peak
            "good": sine(196, 1.0, amp=0.25),        # about -12 dBFS peak
            "turn_down": sine(196, 1.0, amp=0.7),    # about -3 dBFS peak
        }
        for expected, signal in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(analyze_levels(signal)["advice"], expected)

    def test_clipping_is_reported_even_at_moderate_rms(self):
        from audio.levels import analyze_levels
        x = sine(196, 1.0, amp=0.1)
        x[1000:1010] = 1.0
        result = analyze_levels(x)
        self.assertEqual(result["advice"], "turn_down")
        self.assertEqual(result["clipped_samples"], 10)

    def test_levels_in_dbfs(self):
        from audio.levels import analyze_levels
        r = analyze_levels(sine(1000, 1.0, amp=0.5))
        self.assertAlmostEqual(r["peak_dbfs"], -6.0, delta=0.1)
        self.assertAlmostEqual(r["rms_dbfs"], -9.0, delta=0.1)


class NoiseGateTests(unittest.TestCase):
    def test_gate_off_by_default_changes_nothing(self):
        hum = sine(60, 0.5, amp=0.001)
        out = run(Engine(EngineConfig(samplerate=SR)), hum)[:, 0]
        self.assertGreater(rms(out[SR // 10:]), 0.0006)

    def test_gate_silences_hum_but_passes_notes(self):
        e = Engine(EngineConfig(samplerate=SR, gate_open_db=-50))
        hum = sine(60, 0.5, amp=0.001)           # about -60 dBFS: below the gate
        note = sine(196, 0.5, amp=0.1)           # about -20 dBFS: opens it
        out_hum = run(e, hum)[:, 0]
        self.assertLess(rms(out_hum[SR // 4:]), rms(hum) * 0.03, "hum should be >30 dB down once the gate closes")
        out_note = run(e, note)[:, 0]
        self.assertGreater(rms(out_note[SR // 10:]), rms(note) * 0.95, "notes pass at ~unity")

    def test_hysteresis_prevents_chatter_on_a_decaying_note(self):
        from audio.dsp import NoiseGate
        g = NoiseGate(-40, -46, SR, 32)
        t = np.arange(SR) / SR
        tail = (0.02 * np.exp(-2.5 * t) * np.sin(2 * np.pi * 196 * t)).astype(np.float32)  # -34 dB → far below
        flips, last = 0, g.is_open
        for s in range(0, len(tail), 32):
            g.process(tail[s:s + 32].copy())
            flips += g.is_open != last
            last = g.is_open
        self.assertLessEqual(flips, 2, "open once, close once, without chattering")

    def test_input_meter_shows_the_ungated_level(self):
        e = Engine(EngineConfig(samplerate=SR, gate_open_db=-30))
        run(e, sine(60, 0.3, amp=0.003))         # about -50 dBFS, gated
        self.assertGreater(e.snapshot()["input_peak_dbfs"], -55)


if __name__ == "__main__":
    unittest.main()
