"""Synthetic take hesitation detection across tempos (80, 120, 160 strums/min).

Models and evaluates tools/ears onset detection and hesitation analysis using
deterministic physical-model guitar takes from tools/virtual_guitar/guitar.py.

Asserts:
  1. Onset recall and precision across 80, 120, and 160 strums/min.
  2. Planted hesitation detection within ±30 ms of ground-truth recovery strum.
  3. Extra delay accuracy within ±30 ms of planted pause.
  4. Zero false-positive hesitation detections on clean, steady takes.
  5. Distinction between hesitation (> 1.6x interval) vs late/early rubato.
  6. Robustness through audio.Engine DSP filtering and Freeverb reverberation.
  7. End-to-end TakeReport integration with WAV + JSON sidecar metadata.
"""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from audio.fileio import write_wav
from tools.ears.analyze import (
    analyze_take,
    analyze_timing,
    detect_onsets,
)
from tools.virtual_guitar.guitar import (
    CHORDS,
    _add_strum,
    _pickup_and_body,
)
from tools.virtual_guitar.render import render_virtual_guitar

SR = 48000


def synthesize_synthetic_take(
    strum_times_s: list[float],
    samplerate: int = SR,
    seed: int = 42,
    chords: tuple = CHORDS,
    lead_in_s: float = 0.0,
    sustain_s: float = 1.0,
    level: float = 0.55,
) -> np.ndarray:
    """Render deterministic physical-model guitar chords at specified onset times."""
    if not strum_times_s:
        return np.zeros(0, dtype=np.float32)

    total_seconds = max(strum_times_s) + 1.2 + lead_in_s
    total_frames = int(round(total_seconds * samplerate))
    output = np.zeros(total_frames, dtype=np.float64)
    rng = np.random.default_rng(seed)

    for i, t in enumerate(strum_times_s):
        chord_idx = (i // 4) % len(chords)
        _, frets = chords[chord_idx]
        is_downstroke = (i % 2 == 0)
        vel = rng.uniform(0.75, 0.88) if is_downstroke else rng.uniform(0.50, 0.65)
        _add_strum(
            output,
            t + lead_in_s,
            frets,
            samplerate,
            rng,
            velocity=vel,
            direction="down" if is_downstroke else "up",
            sustain=sustain_s,
        )

    output = _pickup_and_body(output, samplerate)
    peak = float(np.max(np.abs(output)))
    if peak > 0:
        output *= (level / peak)
    return output.astype(np.float32)


def generate_strum_schedule(
    strum_count: int,
    rate_strums_min: float,
    start_s: float = 0.35,
    hesitation_indices: dict[int, float] | None = None,
) -> tuple[list[float], dict[int, dict]]:
    """Generate ground truth onset timestamps and hesitation metadata.

    Args:
        strum_count: Number of strums in the schedule.
        rate_strums_min: Strums per minute (e.g. 80, 120, 160).
        start_s: Initial onset time in seconds.
        hesitation_indices: Mapping from strum index -> extra delay in seconds.

    Returns:
        times: List of ground-truth onset timestamps in seconds.
        ground_truth_hesitations: Dict mapping strum index -> metadata dict.
    """
    interval_s = 60.0 / rate_strums_min
    hes_map = hesitation_indices or {}
    times = []
    ground_truth = {}
    current_time = start_s

    for i in range(strum_count):
        extra_delay = hes_map.get(i, 0.0)
        if extra_delay > 0.0:
            current_time += extra_delay
            ground_truth[i] = {
                "recovery_index": i,
                "recovery_time_ms": round(current_time * 1000.0, 1),
                "expected_interval_ms": round(interval_s * 1000.0, 1),
                "actual_interval_ms": round((interval_s + extra_delay) * 1000.0, 1),
                "extra_delay_ms": round(extra_delay * 1000.0, 1),
            }
        times.append(current_time)
        current_time += interval_s

    return times, ground_truth


class EarsSyntheticTempoTests(unittest.TestCase):
    """Test suite evaluating tools/ears performance on virtual guitar takes across tempos."""

    def _evaluate_take(
        self,
        rate_strums_min: float,
        extra_delay_s: float,
        seed: int = 42,
        strum_count: int = 16,
        hesitation_index: int = 8,
    ) -> dict:
        """Run single evaluation and return quantitative diagnostic dictionary."""
        interval_s = 60.0 / rate_strums_min
        times, gt_hes = generate_strum_schedule(
            strum_count=strum_count,
            rate_strums_min=rate_strums_min,
            hesitation_indices={hesitation_index: extra_delay_s} if extra_delay_s > 0 else None,
        )

        audio = synthesize_synthetic_take(times, samplerate=SR, seed=seed)
        onsets = detect_onsets(audio, SR)
        _, intervals, median, stability, findings = analyze_timing(onsets)

        # Onset matching against ground truth (within 30 ms)
        matched_gt = set()
        matched_onsets = 0
        onset_errors = []
        for o in onsets:
            diffs = [abs(o - t * 1000.0) for t in times]
            min_diff = min(diffs)
            best_gt = int(np.argmin(diffs))
            if min_diff <= 30.0 and best_gt not in matched_gt:
                matched_gt.add(best_gt)
                matched_onsets += 1
                onset_errors.append(min_diff)

        onset_recall = matched_onsets / len(times)
        onset_precision = matched_onsets / len(onsets) if len(onsets) > 0 else 0.0
        onset_fp = len(onsets) - matched_onsets

        # Hesitation evaluation
        detected_hes = [f for f in findings if f["type"] == "hesitation"]
        planted_target = gt_hes.get(hesitation_index)
        hesitation_found = False
        hesitation_timing_error = None
        hesitation_extra_error = None
        spurious_hesitations = 0

        for h in detected_hes:
            if planted_target is not None:
                diff = abs(h["at_ms"] - planted_target["recovery_time_ms"])
                if diff <= 30.0 and not hesitation_found:
                    hesitation_found = True
                    hesitation_timing_error = diff
                    hesitation_extra_error = abs(h["extra_ms"] - planted_target["extra_delay_ms"])
                    continue
            spurious_hesitations += 1

        hes_recall = 1.0 if (planted_target is None or hesitation_found) else 0.0

        return {
            "rate_strums_min": rate_strums_min,
            "interval_ms": interval_s * 1000.0,
            "planted_strums": len(times),
            "detected_onsets": len(onsets),
            "onset_recall": onset_recall,
            "onset_precision": onset_precision,
            "onset_fp": onset_fp,
            "mean_onset_error_ms": float(np.mean(onset_errors)) if onset_errors else 0.0,
            "max_onset_error_ms": float(np.max(onset_errors)) if onset_errors else 0.0,
            "hesitation_recall": hes_recall,
            "spurious_hesitations": spurious_hesitations,
            "hesitation_timing_error_ms": hesitation_timing_error,
            "hesitation_extra_error_ms": hesitation_extra_error,
            "median_interval_ms": median,
            "stability": stability,
            "findings_count": len(findings),
        }

    def test_tempo_80_strums_per_min_hesitation_recall_and_zero_fp(self):
        """At 80 strums/min (750 ms interval), planted 500 ms pause is found within ±30 ms."""
        res = self._evaluate_take(rate_strums_min=80.0, extra_delay_s=0.500, seed=10)
        self.assertEqual(res["onset_recall"], 1.0)
        self.assertEqual(res["onset_precision"], 1.0)
        self.assertEqual(res["onset_fp"], 0)
        self.assertEqual(res["hesitation_recall"], 1.0)
        self.assertEqual(res["spurious_hesitations"], 0)
        self.assertLessEqual(res["hesitation_timing_error_ms"], 30.0)
        self.assertLessEqual(res["hesitation_extra_error_ms"], 30.0)
        self.assertAlmostEqual(res["median_interval_ms"], 750.0, delta=15.0)

    def test_tempo_120_strums_per_min_hesitation_recall_and_zero_fp(self):
        """At 120 strums/min (500 ms interval), planted 400 ms pause is found within ±30 ms."""
        res = self._evaluate_take(rate_strums_min=120.0, extra_delay_s=0.400, seed=20)
        self.assertEqual(res["onset_recall"], 1.0)
        self.assertEqual(res["onset_precision"], 1.0)
        self.assertEqual(res["onset_fp"], 0)
        self.assertEqual(res["hesitation_recall"], 1.0)
        self.assertEqual(res["spurious_hesitations"], 0)
        self.assertLessEqual(res["hesitation_timing_error_ms"], 30.0)
        self.assertLessEqual(res["hesitation_extra_error_ms"], 30.0)
        self.assertAlmostEqual(res["median_interval_ms"], 500.0, delta=15.0)

    def test_tempo_160_strums_per_min_hesitation_recall_and_zero_fp(self):
        """At 160 strums/min (375 ms interval), planted 350 ms pause is found within ±30 ms."""
        res = self._evaluate_take(rate_strums_min=160.0, extra_delay_s=0.350, seed=30)
        self.assertEqual(res["onset_recall"], 1.0)
        self.assertEqual(res["onset_precision"], 1.0)
        self.assertEqual(res["onset_fp"], 0)
        self.assertEqual(res["hesitation_recall"], 1.0)
        self.assertEqual(res["spurious_hesitations"], 0)
        self.assertLessEqual(res["hesitation_timing_error_ms"], 30.0)
        self.assertLessEqual(res["hesitation_extra_error_ms"], 30.0)
        self.assertAlmostEqual(res["median_interval_ms"], 375.0, delta=15.0)

    def test_multi_seed_monte_carlo_onset_and_gap_recall_across_all_tempos(self):
        """5 independent seeds across all 3 tempos (15 takes, 240 strums) achieve 100% recall."""
        tempos = [80.0, 120.0, 160.0]
        seeds = [1, 7, 42, 101, 888]

        for tempo in tempos:
            interval_s = 60.0 / tempo
            gap_s = max(0.350, interval_s * 0.75)
            total_strums = 0
            total_detected = 0
            total_fp = 0
            hes_found = 0

            for seed in seeds:
                res = self._evaluate_take(rate_strums_min=tempo, extra_delay_s=gap_s, seed=seed)
                total_strums += res["planted_strums"]
                total_detected += res["detected_onsets"]
                total_fp += res["onset_fp"]
                hes_found += int(res["hesitation_recall"])
                self.assertLessEqual(res["hesitation_timing_error_ms"], 30.0)
                self.assertEqual(res["spurious_hesitations"], 0)

            recall = (total_detected - total_fp) / total_strums
            self.assertEqual(recall, 1.0, f"Tempo {tempo} onset recall failed: {recall}")
            self.assertEqual(total_fp, 0, f"Tempo {tempo} had {total_fp} false positive onsets")
            self.assertEqual(hes_found, len(seeds), f"Tempo {tempo} missed a planted hesitation")

    def test_steady_rhythm_clean_takes_zero_false_positives(self):
        """Evenly spaced strums have 0 hesitations and high tempo stability."""
        for tempo in [80.0, 120.0, 160.0]:
            res = self._evaluate_take(rate_strums_min=tempo, extra_delay_s=0.0, seed=77)
            self.assertEqual(res["onset_recall"], 1.0)
            self.assertEqual(res["onset_fp"], 0)
            self.assertEqual(res["findings_count"], 0)
            self.assertEqual(res["spurious_hesitations"], 0)
            self.assertGreaterEqual(res["stability"], 0.98)

    def test_multiple_planted_hesitations_in_extended_take(self):
        """Two separate chord changes (at index 8 and index 16) are both located within ±30 ms."""
        times, gt_hes = generate_strum_schedule(
            strum_count=24,
            rate_strums_min=120.0,
            hesitation_indices={8: 0.400, 16: 0.450},
        )
        audio = synthesize_synthetic_take(times, samplerate=SR, seed=55)
        onsets = detect_onsets(audio, SR)
        self.assertEqual(len(onsets), 24)

        _, _, _, _, findings = analyze_timing(onsets)
        hes = [f for f in findings if f["type"] == "hesitation"]
        self.assertEqual(len(hes), 2)

        # Check hesitation 1
        self.assertAlmostEqual(hes[0]["at_ms"], gt_hes[8]["recovery_time_ms"], delta=30.0)
        self.assertAlmostEqual(hes[0]["extra_ms"], gt_hes[8]["extra_delay_ms"], delta=30.0)

        # Check hesitation 2
        self.assertAlmostEqual(hes[1]["at_ms"], gt_hes[16]["recovery_time_ms"], delta=30.0)
        self.assertAlmostEqual(hes[1]["extra_ms"], gt_hes[16]["extra_delay_ms"], delta=30.0)

    def test_rubato_late_and_early_strums_distinguished_from_hesitation(self):
        """Mild timing irregularities are classified as late/early, not false hesitations."""
        # 120 strums/min (500 ms interval).
        # Normal interval: 500 ms.
        # Late interval: 500 * 1.30 = 650 ms (extra = 150 ms, ratio = 1.3 < 1.6 hesitation threshold).
        # Early interval: 500 * 0.75 = 375 ms (ratio = 0.75 <= 0.80 early threshold).
        times = [0.35 + i * 0.500 for i in range(5)]
        # Add late strum
        times.append(times[-1] + 0.650)
        # Add early strum
        times.append(times[-1] + 0.375)
        # Add remaining regular strums
        for _ in range(5):
            times.append(times[-1] + 0.500)

        audio = synthesize_synthetic_take(times, samplerate=SR, seed=99)
        onsets = detect_onsets(audio, SR)
        self.assertEqual(len(onsets), len(times))

        _, _, _, _, findings = analyze_timing(onsets)
        hesitations = [f for f in findings if f["type"] == "hesitation"]
        late_findings = [f for f in findings if f["type"] == "late"]
        early_findings = [f for f in findings if f["type"] == "early"]

        self.assertEqual(len(hesitations), 0, "Mild drag must not trigger a false hesitation")
        self.assertEqual(len(late_findings), 1, "Expected exactly 1 late finding")
        self.assertEqual(len(early_findings), 1, "Expected exactly 1 early finding")
        self.assertAlmostEqual(late_findings[0]["at_ms"], times[5] * 1000.0, delta=30.0)
        self.assertAlmostEqual(early_findings[0]["at_ms"], times[6] * 1000.0, delta=30.0)

    def test_dsp_rendered_take_with_filter_and_reverberation(self):
        """Audio rendered through Engine DSP (biquad low-pass + Freeverb) retains onset precision."""
        for tempo in [80.0, 120.0, 160.0]:
            interval_s = 60.0 / tempo
            gap_s = max(0.350, interval_s * 0.75)
            times, gt_hes = generate_strum_schedule(
                strum_count=16,
                rate_strums_min=tempo,
                hesitation_indices={8: gap_s},
            )
            raw_audio = synthesize_synthetic_take(times, samplerate=SR, seed=12)

            # Render through audio.Engine with filter=0.75 and reverb=0.25
            dsp_audio, _ = render_virtual_guitar(
                raw_audio,
                SR,
                tail_seconds=0.5,
                filter_value=0.75,
                reverb_value=0.25,
            )
            mono_dsp = dsp_audio.mean(axis=1)

            onsets = detect_onsets(mono_dsp, SR)
            self.assertEqual(len(onsets), len(times), f"DSP take at {tempo} tempo missed onsets")

            _, _, _, _, findings = analyze_timing(onsets)
            hes = [f for f in findings if f["type"] == "hesitation"]
            self.assertEqual(len(hes), 1, f"DSP take at {tempo} tempo failed to identify hesitation")
            self.assertAlmostEqual(
                hes[0]["at_ms"],
                gt_hes[8]["recovery_time_ms"],
                delta=30.0,
                msg=f"DSP hesitation timing off by > 30 ms at tempo {tempo}",
            )

    def test_take_report_sidecar_file_pipeline(self):
        """Full end-to-end analyze_take from disk passes metadata and calculates strum rate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            wav_path = tmp_path / "take-tempo120.wav"
            sidecar_path = tmp_path / "take-tempo120.json"

            times, gt_hes = generate_strum_schedule(
                strum_count=16,
                rate_strums_min=120.0,
                hesitation_indices={8: 0.400},
            )
            audio = synthesize_synthetic_take(times, samplerate=SR, seed=42)
            duration_s = len(audio) / SR
            start_unix = 1700100000000

            write_wav(wav_path, audio, SR)
            sidecar_data = {
                "version": 1,
                "take_id": "take-tempo120",
                "wav": wav_path.name,
                "samplerate": SR,
                "frames": len(audio),
                "seconds": round(duration_s, 4),
                "started_unix_ms": start_unix,
                "ended_unix_ms": start_unix + round(duration_s * 1000),
                "source": "synthetic_take_tempo",
            }
            sidecar_path.write_text(json.dumps(sidecar_data, indent=2))

            report = analyze_take(wav_path, sidecar_path)
            self.assertEqual(report.take_id, "take-tempo120")
            self.assertEqual(report.started_unix_ms, start_unix)
            self.assertEqual(report.samplerate, SR)
            self.assertEqual(report.strum_count, 16)
            self.assertTrue(report.judgeable)
            self.assertAlmostEqual(report.strum_rate_per_min, 120.0, delta=4.0)

            hesitations = [f for f in report.findings if f["type"] == "hesitation"]
            self.assertEqual(len(hesitations), 1)
            self.assertAlmostEqual(hesitations[0]["at_ms"], gt_hes[8]["recovery_time_ms"], delta=30.0)
            self.assertIn("1 hesitation(s)", report.summary)

    def test_execution_performance_and_latency(self):
        """Analyze 16-strum take (10s audio) in < 100 ms wall-clock time."""
        times, _ = generate_strum_schedule(strum_count=16, rate_strums_min=100.0)
        audio = synthesize_synthetic_take(times, samplerate=SR, seed=1)

        t0 = time.perf_counter()
        onsets = detect_onsets(audio, SR)
        analyze_timing(onsets)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertLess(elapsed_ms, 100.0, f"Analysis took {elapsed_ms:.1f} ms, expected < 100 ms")


if __name__ == "__main__":
    unittest.main()
