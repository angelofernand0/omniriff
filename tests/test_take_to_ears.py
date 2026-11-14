"""End-to-end integration: consecutive takes through audio.Engine to tools.ears.

Covers the practice coach's before/after progression and take isolation:
  1. Two consecutive takes in ONE audio.Engine run with different planted pauses
     (Take 1: 400 ms pause -> Take 2: 150 ms pause).
  2. Both files exist on disk with distinct take_ids (take-*-1, take-*-2).
  3. tools.ears.analyze_take finds each take's own pause within ±30 ms
     relative to that take's start.
  4. The second report's pause is measurably smaller (extra_ms: 400 ms -> 150 ms,
     severity: moderate -> minor), validating before/after coaching evaluation.
  5. An aborted take (record < 0.5 s) yields judgeable=False (too few strums)
     and does NOT clobber or alter earlier takes.
  6. Dry capture immunity to active DSP effects (filter, reverb) during consecutive takes.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from audio.engine import Engine, EngineConfig
from audio.takes import TakeWriter
from tools.ears.analyze import analyze_take
from tools.virtual_guitar.guitar import (
    CHORDS,
    _add_strum,
    _pickup_and_body,
)

SR = 48000
BLOCK_SIZE = 128


def generate_strum_signal(
    bpm: float = 120.0,
    strum_count: int = 16,
    hesitation_index: int = 8,
    extra_pause_s: float = 0.400,
    seed: int = 42,
    lead_in_s: float = 0.35,
) -> tuple[np.ndarray, list[float]]:
    """Generate continuous physical-model audio stream with known onset times."""
    interval_s = 60.0 / bpm
    times = []
    current_time = lead_in_s

    for i in range(strum_count):
        if i == hesitation_index and extra_pause_s > 0:
            current_time += extra_pause_s
        times.append(current_time)
        current_time += interval_s

    total_frames = int(round((times[-1] + 1.2) * SR))
    signal = np.zeros(total_frames, dtype=np.float64)
    rng = np.random.default_rng(seed)

    for i, t in enumerate(times):
        chord_idx = (i // 4) % len(CHORDS)
        _, frets = CHORDS[chord_idx]
        is_down = (i % 2 == 0)
        _add_strum(
            signal,
            t,
            frets,
            SR,
            rng,
            velocity=0.82 if is_down else 0.55,
            direction="down" if is_down else "up",
            sustain=0.80,
        )

    signal = _pickup_and_body(signal, SR)
    peak = float(np.max(np.abs(signal)))
    audio = (signal * (0.55 / peak if peak else 0.0)).astype(np.float32)
    return audio, times


class TakeToEarsConsecutiveTests(unittest.TestCase):
    """End-to-end coach before/after progression and take isolation tests."""

    def test_two_consecutive_takes_before_after_progression_and_aborted_take_isolation(self):
        """TWO consecutive takes in 1 Engine run (400ms then 150ms pause) + aborted take (<0.5s).

        Verifies:
          - Both takes exist with distinct take_ids.
          - Each report finds its own pause within ±30 ms relative to take start.
          - The second report's pause is measurably smaller (extra_ms drops from 400ms to 150ms).
          - An aborted take (< 0.5 s) gives judgeable=False and does not clobber earlier takes.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            engine = Engine(EngineConfig(samplerate=SR))
            writer = TakeWriter(engine, tmp_path)
            out_buf = np.zeros((BLOCK_SIZE, 1), dtype=np.float32)

            # =================================================================
            # TAKE 1 (BEFORE): 400 ms planted hesitation at strum index 8
            # =================================================================
            audio1, times1 = generate_strum_signal(bpm=120.0, extra_pause_s=0.400, seed=101)
            engine.toggle_loop()  # idle -> recording
            # Frame 0 of take is frame BLOCK_SIZE (action drains on next block)
            take1_start_s = BLOCK_SIZE / SR

            for pos in range(0, len(audio1) - BLOCK_SIZE, BLOCK_SIZE):
                engine.process(audio1[pos:pos + BLOCK_SIZE], out_buf)
            engine.toggle_loop()  # recording -> playing (close loop)
            engine.process(audio1[-BLOCK_SIZE:], out_buf)

            wav1 = writer.poll()
            self.assertIsNotNone(wav1, "TakeWriter must capture finished Take 1")
            self.assertTrue(wav1.exists())
            self.assertTrue(wav1.name.endswith("-1.wav"))
            bytes_take1 = wav1.read_bytes()

            json1_path = wav1.with_suffix(".json")
            self.assertTrue(json1_path.exists())
            meta1 = json.loads(json1_path.read_text())
            self.assertEqual(meta1["source"], "loop")

            rep1 = analyze_take(wav1)
            self.assertTrue(rep1.judgeable, "Take 1 (16 strums) must be judgeable")
            self.assertEqual(rep1.take_id, meta1["take_id"])
            self.assertEqual(rep1.started_unix_ms, meta1["started_unix_ms"])
            self.assertEqual(rep1.strum_count, 16)

            # Assert Take 1 hesitation detection (take-relative ±30 ms)
            hesitations1 = [f for f in rep1.findings if f["type"] in ("hesitation", "late")]
            self.assertEqual(len(hesitations1), 1, "Take 1 must have exactly 1 pause finding")
            h1 = hesitations1[0]
            expected_pause1_ms = (times1[8] - take1_start_s) * 1000.0
            error1 = abs(h1["at_ms"] - expected_pause1_ms)
            self.assertLessEqual(
                error1,
                30.0,
                f"Take 1 pause at {h1['at_ms']:.1f} ms differed by {error1:.1f} ms from {expected_pause1_ms:.1f} ms",
            )
            self.assertAlmostEqual(h1["extra_ms"], 400.0, delta=30.0)
            self.assertIn(h1["severity"], ("moderate", "severe"))

            # =================================================================
            # TAKE 2 (AFTER): 150 ms planted pause at strum index 8 (improved)
            # =================================================================
            audio2, times2 = generate_strum_signal(bpm=120.0, extra_pause_s=0.150, seed=202)
            # Clear looper: playing -> idle
            engine.toggle_loop()
            engine.process(audio2[:BLOCK_SIZE], out_buf)

            # Start recording Take 2: idle -> recording
            engine.toggle_loop()
            take2_start_s = (2 * BLOCK_SIZE) / SR

            for pos in range(BLOCK_SIZE, len(audio2) - BLOCK_SIZE, BLOCK_SIZE):
                engine.process(audio2[pos:pos + BLOCK_SIZE], out_buf)
            engine.toggle_loop()  # recording -> playing (close loop)
            engine.process(audio2[-BLOCK_SIZE:], out_buf)

            wav2 = writer.poll()
            self.assertIsNotNone(wav2, "TakeWriter must capture finished Take 2")
            self.assertTrue(wav2.exists())
            self.assertTrue(wav2.name.endswith("-2.wav"))
            bytes_take2 = wav2.read_bytes()

            json2_path = wav2.with_suffix(".json")
            self.assertTrue(json2_path.exists())
            meta2 = json.loads(json2_path.read_text())

            rep2 = analyze_take(wav2)
            self.assertTrue(rep2.judgeable, "Take 2 (16 strums) must be judgeable")
            self.assertEqual(rep2.take_id, meta2["take_id"])
            self.assertEqual(rep2.started_unix_ms, meta2["started_unix_ms"])
            self.assertEqual(rep2.strum_count, 16)

            # Assert Take 2 hesitation detection (take-relative ±30 ms)
            hesitations2 = [f for f in rep2.findings if f["type"] in ("hesitation", "late")]
            self.assertEqual(len(hesitations2), 1, "Take 2 must have exactly 1 pause finding")
            h2 = hesitations2[0]
            expected_pause2_ms = (times2[8] - take2_start_s) * 1000.0
            error2 = abs(h2["at_ms"] - expected_pause2_ms)
            self.assertLessEqual(
                error2,
                30.0,
                f"Take 2 pause at {h2['at_ms']:.1f} ms differed by {error2:.1f} ms from {expected_pause2_ms:.1f} ms",
            )
            self.assertAlmostEqual(h2["extra_ms"], 150.0, delta=30.0)
            self.assertEqual(h2["severity"], "minor")

            # =================================================================
            # COACH PROGRESSION ASSERTIONS (BEFORE vs AFTER)
            # =================================================================
            self.assertNotEqual(wav1, wav2)
            self.assertNotEqual(meta1["take_id"], meta2["take_id"])
            self.assertLessEqual(meta1["started_unix_ms"], meta2["started_unix_ms"])

            # Verify Take 1 on disk was NOT clobbered by Take 2
            self.assertEqual(wav1.read_bytes(), bytes_take1)

            # Verify second report's pause is measurably smaller
            self.assertLess(
                h2["extra_ms"],
                h1["extra_ms"],
                f"Take 2 pause ({h2['extra_ms']} ms) must be smaller than Take 1 pause ({h1['extra_ms']} ms)",
            )
            pause_reduction = h1["extra_ms"] - h2["extra_ms"]
            self.assertGreaterEqual(
                pause_reduction,
                200.0,
                f"Coach must detect measurable pause reduction (got {pause_reduction:.1f} ms)",
            )

            # =================================================================
            # TAKE 3 (ABORTED TAKE): Record < 0.5 s in the SAME Engine run
            # =================================================================
            engine.toggle_loop()  # playing -> idle
            engine.process(audio1[:BLOCK_SIZE], out_buf)

            engine.toggle_loop()  # idle -> recording
            # Record 0.35 s of audio (contains only 1 strum, well below MIN_STRUMS=4)
            aborted_len = int(0.35 * SR)
            for pos in range(0, aborted_len - BLOCK_SIZE, BLOCK_SIZE):
                engine.process(audio1[pos:pos + BLOCK_SIZE], out_buf)
            engine.toggle_loop()  # recording -> playing (close aborted take)
            engine.process(audio1[:BLOCK_SIZE], out_buf)

            wav3 = writer.poll()
            self.assertIsNotNone(wav3, "TakeWriter captures the aborted recording buffer")
            self.assertTrue(wav3.exists())
            self.assertTrue(wav3.name.endswith("-3.wav"))

            meta3 = json.loads(wav3.with_suffix(".json").read_text())
            self.assertLess(meta3["seconds"], 0.5, "Aborted take duration must be < 0.5 s")

            rep3 = analyze_take(wav3)
            self.assertFalse(rep3.judgeable, "Aborted take (< 0.5 s) must have judgeable=False")
            self.assertLess(rep3.strum_count, 4)
            self.assertIn("too few to judge timing", rep3.summary)
            self.assertEqual(rep3.findings, [])

            # =================================================================
            # CLOBBER RESISTANCE CHECK: Earlier takes remain 100% intact
            # =================================================================
            self.assertEqual(wav1.read_bytes(), bytes_take1, "Take 1 clobbered by aborted take")
            self.assertEqual(wav2.read_bytes(), bytes_take2, "Take 2 clobbered by aborted take")

            # Re-verifying analysis on earlier takes produces identical results
            re_rep1 = analyze_take(wav1)
            re_rep2 = analyze_take(wav2)
            self.assertTrue(re_rep1.judgeable)
            self.assertTrue(re_rep2.judgeable)
            self.assertEqual(re_rep1.take_id, meta1["take_id"])
            self.assertEqual(re_rep2.take_id, meta2["take_id"])

    def test_consecutive_takes_under_active_dsp(self):
        """Active live DSP (filter 0.3, reverb 0.8) does not contaminate dry captured takes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            engine = Engine(EngineConfig(samplerate=SR))
            engine.set_filter(0.3)
            engine.set_reverb(0.8)

            writer = TakeWriter(engine, tmp_path)
            out_buf = np.zeros((BLOCK_SIZE, 1), dtype=np.float32)

            # Take 1 (400 ms pause)
            audio1, times1 = generate_strum_signal(bpm=120.0, extra_pause_s=0.400, seed=301)
            engine.toggle_loop()
            for pos in range(0, len(audio1) - BLOCK_SIZE, BLOCK_SIZE):
                engine.process(audio1[pos:pos + BLOCK_SIZE], out_buf)
            engine.toggle_loop()
            engine.process(audio1[-BLOCK_SIZE:], out_buf)

            wav1 = writer.poll()
            rep1 = analyze_take(wav1)
            self.assertTrue(rep1.judgeable)
            self.assertEqual(rep1.strum_count, 16)
            h1 = rep1.findings[0]
            self.assertAlmostEqual(h1["extra_ms"], 400.0, delta=30.0)

            # Take 2 (150 ms pause)
            audio2, times2 = generate_strum_signal(bpm=120.0, extra_pause_s=0.150, seed=402)
            engine.toggle_loop()
            engine.process(audio2[:BLOCK_SIZE], out_buf)
            engine.toggle_loop()
            for pos in range(BLOCK_SIZE, len(audio2) - BLOCK_SIZE, BLOCK_SIZE):
                engine.process(audio2[pos:pos + BLOCK_SIZE], out_buf)
            engine.toggle_loop()
            engine.process(audio2[-BLOCK_SIZE:], out_buf)

            wav2 = writer.poll()
            rep2 = analyze_take(wav2)
            self.assertTrue(rep2.judgeable)
            self.assertEqual(rep2.strum_count, 16)
            h2 = rep2.findings[0]
            self.assertAlmostEqual(h2["extra_ms"], 150.0, delta=30.0)

            # Assert coach progression holds even under wet monitor effects
            self.assertLess(h2["extra_ms"], h1["extra_ms"])

    def test_aborted_take_zero_length_recording_safely_ignored(self):
        """Immediately toggling loop before any frames are processed returns to IDLE cleanly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            engine = Engine(EngineConfig(samplerate=SR))
            writer = TakeWriter(engine, tmp_path)
            out_buf = np.zeros((BLOCK_SIZE, 1), dtype=np.float32)

            # Take 1: valid take
            audio1, _ = generate_strum_signal(bpm=120.0, extra_pause_s=0.400, seed=501)
            engine.toggle_loop()
            for pos in range(0, len(audio1) - BLOCK_SIZE, BLOCK_SIZE):
                engine.process(audio1[pos:pos + BLOCK_SIZE], out_buf)
            engine.toggle_loop()
            engine.process(audio1[-BLOCK_SIZE:], out_buf)

            wav1 = writer.poll()
            self.assertIsNotNone(wav1)
            bytes1 = wav1.read_bytes()

            # Zero-length abort: toggle to recording, then immediately toggle without processing
            engine.toggle_loop()  # playing -> idle
            engine.process(audio1[:BLOCK_SIZE], out_buf)

            engine.looper.toggle()  # idle -> recording
            self.assertEqual(engine.looper.length, 0)
            engine.looper.toggle()  # recording -> idle (length == 0 branch)
            self.assertEqual(engine.looper.state, "idle")

            # TakeWriter poll returns None because takes_finished was not incremented
            wav_none = writer.poll()
            self.assertIsNone(wav_none)

            # Take 1 remains untouched
            self.assertEqual(wav1.read_bytes(), bytes1)

    def test_consecutive_takes_variable_tempo(self):
        """Coach before/after progression holds across tempo variations (100 BPM -> 140 BPM)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            engine = Engine(EngineConfig(samplerate=SR))
            writer = TakeWriter(engine, tmp_path)
            out_buf = np.zeros((BLOCK_SIZE, 1), dtype=np.float32)

            # Take 1: 100 BPM with 450 ms pause
            audio1, times1 = generate_strum_signal(bpm=100.0, extra_pause_s=0.450, seed=601)
            engine.toggle_loop()
            for pos in range(0, len(audio1) - BLOCK_SIZE, BLOCK_SIZE):
                engine.process(audio1[pos:pos + BLOCK_SIZE], out_buf)
            engine.toggle_loop()
            engine.process(audio1[-BLOCK_SIZE:], out_buf)

            wav1 = writer.poll()
            rep1 = analyze_take(wav1)
            self.assertTrue(rep1.judgeable)
            self.assertAlmostEqual(rep1.strum_rate_per_min, 100.0, delta=5.0)
            h1 = rep1.findings[0]
            self.assertAlmostEqual(h1["extra_ms"], 450.0, delta=35.0)

            # Take 2: 140 BPM with 200 ms pause
            audio2, times2 = generate_strum_signal(bpm=140.0, extra_pause_s=0.200, seed=702)
            engine.toggle_loop()
            engine.process(audio2[:BLOCK_SIZE], out_buf)
            engine.toggle_loop()
            for pos in range(BLOCK_SIZE, len(audio2) - BLOCK_SIZE, BLOCK_SIZE):
                engine.process(audio2[pos:pos + BLOCK_SIZE], out_buf)
            engine.toggle_loop()
            engine.process(audio2[-BLOCK_SIZE:], out_buf)

            wav2 = writer.poll()
            rep2 = analyze_take(wav2)
            self.assertTrue(rep2.judgeable)
            self.assertAlmostEqual(rep2.strum_rate_per_min, 140.0, delta=5.0)
            h2 = rep2.findings[0]
            self.assertAlmostEqual(h2["extra_ms"], 200.0, delta=30.0)

            # Pause reduced and rate increased
            self.assertLess(h2["extra_ms"], h1["extra_ms"])
            self.assertGreater(rep2.strum_rate_per_min, rep1.strum_rate_per_min)


if __name__ == "__main__":
    unittest.main()
