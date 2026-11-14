"""End-to-end integration: virtual guitar -> audio.Engine -> TakeWriter -> tools.ears.

Tests the full signal chain path:
  1. Deterministic physical-model guitar strums fed into real audio.Engine
     via process() in 128-frame blocks (headless, no hardware devices).
  2. Looper toggling via engine.toggle_loop(): idle -> recording -> playing (close).
  3. Off-real-time capture: TakeWriter(engine, tmpdir).poll() saves WAV + JSON.
  4. tools.ears.analyze_take finds planted hesitations within ±30 ms relative
     to the take start.
  5. Sidecar take_id and started_unix_ms pass through into TakeReport.
  6. Sequential takes increment take index (-1, -2) without overwriting.
  7. Dry take capture immunity to active real-time filter and reverb DSP.
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


class TakeToEarsTests(unittest.TestCase):
    """End-to-end integration tests connecting audio.Engine, TakeWriter, and tools.ears."""

    def test_end_to_end_planted_hesitation_capture_and_ears_detection(self):
        """Audio stream through 128-frame process() captured to WAV+JSON; Ears detects pause."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            engine = Engine(EngineConfig(samplerate=SR))
            writer = TakeWriter(engine, tmp_path)

            audio, times = generate_strum_signal(bpm=120.0, extra_pause_s=0.400)
            out_buf = np.zeros((BLOCK_SIZE, 1), dtype=np.float32)

            take_start_frame = None
            rec_start_time = 0.10
            rec_end_time = times[-1] + 0.50

            pos = 0
            while pos + BLOCK_SIZE <= len(audio):
                cur_t = pos / SR
                if take_start_frame is None and cur_t >= rec_start_time:
                    engine.toggle_loop()
                    take_start_frame = pos + BLOCK_SIZE  # action drains on next block
                elif cur_t >= rec_end_time and engine.looper.state == "recording":
                    engine.toggle_loop()

                block = audio[pos:pos + BLOCK_SIZE]
                engine.process(block, out_buf)
                pos += BLOCK_SIZE

            # Poll writer to save WAV + JSON sidecar
            wav_path = writer.poll()
            self.assertIsNotNone(wav_path, "TakeWriter must capture finished take")
            self.assertTrue(wav_path.exists())
            json_path = wav_path.with_suffix(".json")
            self.assertTrue(json_path.exists())

            # Verify sidecar structure
            sidecar = json.loads(json_path.read_text())
            self.assertEqual(sidecar["source"], "loop")
            self.assertEqual(sidecar["samplerate"], SR)
            self.assertGreater(sidecar["frames"], 0)

            # Analyze take with tools.ears
            report = analyze_take(wav_path, json_path)
            self.assertTrue(report.judgeable)
            self.assertEqual(report.strum_count, 16)

            # Assert sidecar fields pass through to TakeReport
            self.assertEqual(report.take_id, sidecar["take_id"])
            self.assertEqual(report.started_unix_ms, sidecar["started_unix_ms"])

            # Assert planted hesitation found within ±30 ms relative to take start
            hesitations = [f for f in report.findings if f["type"] == "hesitation"]
            self.assertEqual(len(hesitations), 1, "Ears must find exactly 1 planted hesitation")
            h = hesitations[0]

            take_start_s = take_start_frame / SR
            expected_recovery_take_ms = (times[8] - take_start_s) * 1000.0
            timing_error = abs(h["at_ms"] - expected_recovery_take_ms)

            self.assertLessEqual(
                timing_error,
                30.0,
                f"Hesitation at_ms={h['at_ms']:.1f} ms differed by {timing_error:.1f} ms from "
                f"expected {expected_recovery_take_ms:.1f} ms",
            )
            self.assertAlmostEqual(h["extra_ms"], 400.0, delta=30.0)
            self.assertIn(h["severity"], ("moderate", "severe"))

    def test_sequential_takes_do_not_overwrite_and_retain_distinct_sidecars(self):
        """A second take increments take index (-1, -2) and preserves the first take."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            engine = Engine(EngineConfig(samplerate=SR))
            writer = TakeWriter(engine, tmp_path)
            out_buf = np.zeros((BLOCK_SIZE, 1), dtype=np.float32)

            # --- TAKE 1: 400 ms pause ---
            audio1, _ = generate_strum_signal(bpm=120.0, extra_pause_s=0.400, seed=10)
            engine.toggle_loop()  # start recording
            for pos in range(0, len(audio1) - BLOCK_SIZE, BLOCK_SIZE):
                engine.process(audio1[pos:pos + BLOCK_SIZE], out_buf)
            engine.toggle_loop()  # recording -> playing (finish)
            engine.process(audio1[-BLOCK_SIZE:], out_buf)

            wav1 = writer.poll()
            self.assertIsNotNone(wav1)
            bytes_take1 = wav1.read_bytes()
            meta1 = json.loads(wav1.with_suffix(".json").read_text())

            # --- TAKE 2: 500 ms pause ---
            audio2, _ = generate_strum_signal(bpm=120.0, extra_pause_s=0.500, seed=20)
            engine.toggle_loop()  # playing -> idle (clear)
            engine.process(audio2[:BLOCK_SIZE], out_buf)
            engine.toggle_loop()  # idle -> recording
            for pos in range(BLOCK_SIZE, len(audio2) - BLOCK_SIZE, BLOCK_SIZE):
                engine.process(audio2[pos:pos + BLOCK_SIZE], out_buf)
            engine.toggle_loop()  # recording -> playing
            engine.process(audio2[-BLOCK_SIZE:], out_buf)

            wav2 = writer.poll()
            self.assertIsNotNone(wav2)
            meta2 = json.loads(wav2.with_suffix(".json").read_text())

            # Assert distinct files on disk
            self.assertNotEqual(wav1, wav2)
            self.assertTrue(wav1.exists())
            self.assertTrue(wav2.exists())
            self.assertTrue(wav1.name.endswith("-1.wav"))
            self.assertTrue(wav2.name.endswith("-2.wav"))

            # Assert Take 1 was NOT overwritten or corrupted
            self.assertEqual(wav1.read_bytes(), bytes_take1)
            self.assertNotEqual(meta1["take_id"], meta2["take_id"])
            self.assertLessEqual(meta1["started_unix_ms"], meta2["started_unix_ms"])

            # Assert both analyze cleanly with distinct metadata pass-through
            r1 = analyze_take(wav1)
            r2 = analyze_take(wav2)
            self.assertEqual(r1.take_id, meta1["take_id"])
            self.assertEqual(r2.take_id, meta2["take_id"])
            self.assertEqual(r1.started_unix_ms, meta1["started_unix_ms"])
            self.assertEqual(r2.started_unix_ms, meta2["started_unix_ms"])
            self.assertEqual(r1.strum_count, 16)
            self.assertEqual(r2.strum_count, 16)

    def test_multi_tempo_real_engine_loop_capture(self):
        """80 strums/min and 160 strums/min streamed through Engine detect pause within ±30 ms."""
        for bpm, pause_s in [(80.0, 0.500), (160.0, 0.350)]:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                engine = Engine(EngineConfig(samplerate=SR))
                writer = TakeWriter(engine, tmp_path)
                out_buf = np.zeros((BLOCK_SIZE, 1), dtype=np.float32)

                audio, times = generate_strum_signal(bpm=bpm, extra_pause_s=pause_s, seed=33)
                engine.toggle_loop()
                # Process all blocks
                for pos in range(0, len(audio) - BLOCK_SIZE, BLOCK_SIZE):
                    engine.process(audio[pos:pos + BLOCK_SIZE], out_buf)
                engine.toggle_loop()
                engine.process(audio[-BLOCK_SIZE:], out_buf)

                wav = writer.poll()
                self.assertIsNotNone(wav)
                rep = analyze_take(wav)
                self.assertEqual(rep.strum_count, 16)

                hes = [f for f in rep.findings if f["type"] == "hesitation"]
                self.assertEqual(len(hes), 1)
                # First block processed after toggle is block 0 (frame 0 of take is frame BLOCK_SIZE)
                expected_take_ms = (times[8] - (BLOCK_SIZE / SR)) * 1000.0
                err = abs(hes[0]["at_ms"] - expected_take_ms)
                self.assertLessEqual(err, 30.0, f"Tempo {bpm} timing error {err:.1f} ms > 30 ms")

    def test_take_writer_dry_capture_immunity_to_active_dsp(self):
        """Active low-pass filter (0.3) and reverb (0.8) on Engine do not smear captured take."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            engine = Engine(EngineConfig(samplerate=SR))
            # Heavily effect the live output
            engine.set_filter(0.3)
            engine.set_reverb(0.8)

            writer = TakeWriter(engine, tmp_path)
            out_buf = np.zeros((BLOCK_SIZE, 1), dtype=np.float32)
            audio, times = generate_strum_signal(bpm=120.0, extra_pause_s=0.400, seed=77)

            engine.toggle_loop()
            for pos in range(0, len(audio) - BLOCK_SIZE, BLOCK_SIZE):
                engine.process(audio[pos:pos + BLOCK_SIZE], out_buf)
            engine.toggle_loop()
            engine.process(audio[-BLOCK_SIZE:], out_buf)

            wav = writer.poll()
            rep = analyze_take(wav)

            # Output buffer is wet, but captured take is dry post-gain: all 16 onsets detected
            self.assertEqual(rep.strum_count, 16)
            hes = [f for f in rep.findings if f["type"] == "hesitation"]
            self.assertEqual(len(hes), 1)
            self.assertAlmostEqual(hes[0]["extra_ms"], 400.0, delta=30.0)

    def test_clean_take_through_engine_zero_hesitations(self):
        """Evenly spaced strums recorded through Engine produce 0 false hesitations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            engine = Engine(EngineConfig(samplerate=SR))
            writer = TakeWriter(engine, tmp_path)
            out_buf = np.zeros((BLOCK_SIZE, 1), dtype=np.float32)

            audio, _ = generate_strum_signal(bpm=120.0, extra_pause_s=0.0, seed=88)
            engine.toggle_loop()
            for pos in range(0, len(audio) - BLOCK_SIZE, BLOCK_SIZE):
                engine.process(audio[pos:pos + BLOCK_SIZE], out_buf)
            engine.toggle_loop()
            engine.process(audio[-BLOCK_SIZE:], out_buf)

            wav = writer.poll()
            rep = analyze_take(wav)
            self.assertEqual(rep.strum_count, 16)
            self.assertEqual(len([f for f in rep.findings if f["type"] == "hesitation"]), 0)
            self.assertGreaterEqual(rep.tempo_stability, 0.98)

    def test_silent_or_sparse_take_marked_not_judgeable(self):
        """Closing a loop with under 4 strums produces a non-judgeable TakeReport."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            engine = Engine(EngineConfig(samplerate=SR))
            writer = TakeWriter(engine, tmp_path)
            out_buf = np.zeros((BLOCK_SIZE, 1), dtype=np.float32)

            # Record 1.5 seconds of silence
            silence_block = np.zeros(BLOCK_SIZE, dtype=np.float32)
            engine.toggle_loop()
            for _ in range(int(1.5 * SR // BLOCK_SIZE)):
                engine.process(silence_block, out_buf)
            engine.toggle_loop()
            engine.process(silence_block, out_buf)

            wav = writer.poll()
            self.assertIsNotNone(wav)
            rep = analyze_take(wav)
            self.assertFalse(rep.judgeable)
            self.assertEqual(rep.strum_count, 0)
            self.assertEqual(rep.findings, [])
            self.assertIn("too few to judge timing", rep.summary)


if __name__ == "__main__":
    unittest.main()
