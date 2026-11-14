"""DI chain degradation robustness tests for tools/ears.

Evaluates tools/ears onset detection and hesitation analysis under real-world
direct-input (DI) hardware impairments:
  (a) 60 Hz mains hum + 10 integer harmonics at -30 dBFS
  (b) White noise floor at -50 dBFS, -40 dBFS, and high-noise threshold (-30 dBFS)
  (c) Hard clipping at 0.5 full scale (ADC overdrive)
  (d) DC offset (+0.05 uncalibrated converter bias)
  (e) Dark pickup (2 kHz low-pass with highpass_hz=1500 documented knob)
  (f) Quiet input peaking at -30 dBFS (low instrument output / passive pickup)

Known limits where Ears fails are marked with @unittest.expectedFailure
without modifying tools/ears thresholds or production code.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

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

SR = 48000


def render_base_take(
    bpm: float = 120.0,
    strum_count: int = 16,
    hesitation_index: int = 8,
    extra_delay_s: float = 0.400,
    seed: int = 42,
    downstroke_vel: float = 0.80,
    upstroke_vel: float = 0.55,
) -> tuple[np.ndarray, list[float], dict]:
    """Generate deterministic physical-model guitar take with a planted hesitation.

    Returns:
        audio: 1D float32 audio signal normalized to peak 0.55 (-5.2 dBFS).
        strum_times_s: List of ground-truth strum timestamps in seconds.
        hesitation_gt: Dict containing ground truth hesitation metadata.
    """
    interval_s = 60.0 / bpm
    times = []
    current_time = 0.35
    hesitation_gt = {}

    for i in range(strum_count):
        if i == hesitation_index and extra_delay_s > 0:
            current_time += extra_delay_s
            hesitation_gt = {
                "recovery_index": i,
                "recovery_time_ms": round(current_time * 1000.0, 1),
                "extra_delay_ms": round(extra_delay_s * 1000.0, 1),
                "expected_interval_ms": round(interval_s * 1000.0, 1),
                "actual_interval_ms": round((interval_s + extra_delay_s) * 1000.0, 1),
            }
        times.append(current_time)
        current_time += interval_s

    total_frames = int(round((times[-1] + 1.2) * SR))
    output = np.zeros(total_frames, dtype=np.float64)
    rng = np.random.default_rng(seed)

    for i, t in enumerate(times):
        chord_idx = (i // 4) % len(CHORDS)
        _, frets = CHORDS[chord_idx]
        is_downstroke = (i % 2 == 0)
        vel = downstroke_vel if is_downstroke else upstroke_vel
        _add_strum(
            output,
            t,
            frets,
            SR,
            rng,
            velocity=vel,
            direction="down" if is_downstroke else "up",
            sustain=0.85,
        )

    output = _pickup_and_body(output, SR)
    peak = float(np.max(np.abs(output)))
    audio = (output * (0.55 / peak if peak else 0.0)).astype(np.float32)
    return audio, times, hesitation_gt


def evaluate_detection(
    audio: np.ndarray,
    times: list[float],
    hesitation_gt: dict,
    highpass_hz: float = 3000.0,
    tolerance_ms: float = 30.0,
) -> dict:
    """Evaluate onset and hesitation detection metrics against ground truth."""
    onsets = detect_onsets(audio, SR, highpass_hz=highpass_hz)
    _, _, median, stability, findings = analyze_timing(onsets)

    # Match onsets within tolerance
    matched_gt = set()
    matched_onsets = 0
    onset_errors = []
    for o in onsets:
        diffs = [abs(o - t * 1000.0) for t in times]
        min_diff = min(diffs)
        best_gt = int(np.argmin(diffs))
        if min_diff <= tolerance_ms and best_gt not in matched_gt:
            matched_gt.add(best_gt)
            matched_onsets += 1
            onset_errors.append(min_diff)

    onset_recall = matched_onsets / len(times) if times else 0.0
    onset_precision = matched_onsets / len(onsets) if len(onsets) > 0 else 0.0
    onset_fp = len(onsets) - matched_onsets

    # Evaluate hesitation detection
    detected_hes = [f for f in findings if f["type"] == "hesitation"]
    hes_found = False
    hes_timing_error = None
    spurious_hesitations = 0

    for h in detected_hes:
        if hesitation_gt:
            diff = abs(h["at_ms"] - hesitation_gt["recovery_time_ms"])
            if diff <= tolerance_ms and not hes_found:
                hes_found = True
                hes_timing_error = diff
                continue
        spurious_hesitations += 1

    hes_recall = 1.0 if (not hesitation_gt or hes_found) else 0.0

    return {
        "strum_count": len(times),
        "detected_count": len(onsets),
        "onset_recall": onset_recall,
        "onset_precision": onset_precision,
        "onset_fp": onset_fp,
        "max_onset_error_ms": float(np.max(onset_errors)) if onset_errors else 0.0,
        "hesitation_recall": hes_recall,
        "spurious_hesitations": spurious_hesitations,
        "hesitation_timing_error_ms": hes_timing_error,
        "median_interval_ms": median,
        "stability": stability,
        "findings": findings,
    }


class EarsRobustnessTests(unittest.TestCase):
    """Test tools/ears under real-world DI signal chain degradation."""

    @classmethod
    def setUpClass(cls):
        cls.audio, cls.times, cls.gt = render_base_take(bpm=120.0, extra_delay_s=0.400)
        cls.clean_audio, cls.clean_times, cls.clean_gt = render_base_take(bpm=120.0, extra_delay_s=0.0)

    def test_60hz_mains_hum_and_harmonics_at_minus_30_dbfs(self):
        """Condition (a): 60 Hz hum + 10 harmonics at -30 dBFS rejected by 3 kHz highpass."""
        # Synthesize 60 Hz fundamental + 10 integer harmonics (120, 180, ..., 600 Hz)
        t_vec = np.arange(len(self.audio)) / SR
        hum = np.zeros_like(self.audio)
        for h in range(1, 11):
            hum += (1.0 / h) * np.sin(2.0 * np.pi * 60.0 * h * t_vec)
        hum_peak = 10.0 ** (-30.0 / 20.0)  # ~0.03162 (-30 dBFS)
        hum = (hum / np.max(np.abs(hum)) * hum_peak).astype(np.float32)

        degraded = self.audio + hum
        res = evaluate_detection(degraded, self.times, self.gt)

        self.assertEqual(res["onset_recall"], 1.0, "All 16 onsets must be detected despite -30 dBFS hum")
        self.assertEqual(res["onset_precision"], 1.0)
        self.assertEqual(res["onset_fp"], 0, "No spurious onsets from mains hum harmonics")
        self.assertEqual(res["hesitation_recall"], 1.0, "Planted hesitation must be found")
        self.assertEqual(res["spurious_hesitations"], 0)
        self.assertLessEqual(res["hesitation_timing_error_ms"], 30.0)

        # Test clean take with hum: verify 0 false hesitations
        t_clean = np.arange(len(self.clean_audio)) / SR
        clean_hum = np.zeros_like(self.clean_audio)
        for h in range(1, 11):
            clean_hum += (1.0 / h) * np.sin(2.0 * np.pi * 60.0 * h * t_clean)
        clean_hum = (clean_hum / np.max(np.abs(clean_hum)) * hum_peak).astype(np.float32)
        clean_degraded = self.clean_audio + clean_hum
        res_clean = evaluate_detection(clean_degraded, self.clean_times, self.clean_gt)
        self.assertEqual(res_clean["spurious_hesitations"], 0)
        self.assertEqual(len(res_clean["findings"]), 0)

    def test_white_noise_floor_at_minus_50_dbfs(self):
        """Condition (b1): White noise floor at -50 dBFS RMS retains 100% recall."""
        rng = np.random.default_rng(1234)
        noise_sigma = 10.0 ** (-50.0 / 20.0)  # ~0.00316 RMS
        noise = rng.normal(0.0, noise_sigma, len(self.audio)).astype(np.float32)

        degraded = self.audio + noise
        res = evaluate_detection(degraded, self.times, self.gt)

        self.assertEqual(res["onset_recall"], 1.0)
        self.assertEqual(res["onset_precision"], 1.0)
        self.assertEqual(res["onset_fp"], 0)
        self.assertEqual(res["hesitation_recall"], 1.0)
        self.assertEqual(res["spurious_hesitations"], 0)
        self.assertLessEqual(res["hesitation_timing_error_ms"], 30.0)

    def test_white_noise_floor_at_minus_40_dbfs(self):
        """Condition (b2): White noise floor at -40 dBFS RMS retains 100% recall."""
        rng = np.random.default_rng(5678)
        noise_sigma = 10.0 ** (-40.0 / 20.0)  # ~0.0100 RMS
        noise = rng.normal(0.0, noise_sigma, len(self.audio)).astype(np.float32)

        degraded = self.audio + noise
        res = evaluate_detection(degraded, self.times, self.gt)

        self.assertEqual(res["onset_recall"], 1.0)
        self.assertEqual(res["onset_precision"], 1.0)
        self.assertEqual(res["onset_fp"], 0)
        self.assertEqual(res["hesitation_recall"], 1.0)
        self.assertEqual(res["spurious_hesitations"], 0)
        self.assertLessEqual(res["hesitation_timing_error_ms"], 30.0)

    @unittest.expectedFailure
    def test_white_noise_floor_at_minus_30_dbfs_masks_soft_upstrokes(self):
        """Condition (b3) KNOWN LIMIT: -30 dBFS white noise suppresses 9 dB rise on soft upstrokes.

        Known limit: When wideband white noise floor reaches -30 dBFS (SNR ~ 24 dB relative
        to peak guitar signal), the broadband energy elevation across the 3 kHz highpass
        band suppresses the 9 dB log-energy rise threshold for quieter upstrokes (e.g. 0.4 velocity),
        reducing onset recall below 100%.
        """
        rng = np.random.default_rng(9999)
        noise_sigma = 10.0 ** (-30.0 / 20.0)  # ~0.0316 RMS
        noise = rng.normal(0.0, noise_sigma, len(self.audio)).astype(np.float32)

        degraded = self.audio + noise
        res = evaluate_detection(degraded, self.times, self.gt)

        # Expected to fail: soft upstrokes are masked by the high noise floor
        self.assertEqual(
            res["onset_recall"],
            1.0,
            f"Expected failure: -30 dBFS noise masked {res['strum_count'] - res['detected_count']} soft upstrokes",
        )

    def test_hard_clipping_at_half_full_scale(self):
        """Condition (c): Hard clipping at 0.5 full scale preserves attack transients."""
        # Boost base audio by 6 dB and hard-clip at [-0.5, 0.5]
        clipped = np.clip(self.audio * 2.0, -0.5, 0.5)

        res = evaluate_detection(clipped, self.times, self.gt)
        self.assertEqual(res["onset_recall"], 1.0, "Clipped signal must still detect all onsets")
        self.assertEqual(res["onset_precision"], 1.0)
        self.assertEqual(res["onset_fp"], 0, "No false onsets from square clipping edges")
        self.assertEqual(res["hesitation_recall"], 1.0)
        self.assertEqual(res["spurious_hesitations"], 0)
        self.assertLessEqual(res["hesitation_timing_error_ms"], 30.0)

    def test_dc_offset_rejection(self):
        """Condition (d): +0.05 DC offset is completely rejected by 3 kHz highpass."""
        offset_audio = self.audio + 0.05

        res = evaluate_detection(offset_audio, self.times, self.gt)
        self.assertEqual(res["onset_recall"], 1.0)
        self.assertEqual(res["onset_precision"], 1.0)
        self.assertEqual(res["onset_fp"], 0)
        self.assertEqual(res["hesitation_recall"], 1.0)
        self.assertEqual(res["spurious_hesitations"], 0)
        self.assertLessEqual(res["hesitation_timing_error_ms"], 30.0)

    def test_dark_pickup_with_documented_highpass_knob(self):
        """Condition (e1): 2 kHz low-pass with documented highpass_hz=1500 knob achieves 100% recall."""
        # 4th-order Butterworth low-pass at 2000 Hz modeling a dark humbucker with rolled-off tone
        sos_lp = butter(4, 2000.0, btype="lowpass", fs=SR, output="sos")
        dark_audio = sosfilt(sos_lp, self.audio.astype(np.float64)).astype(np.float32)

        # Call with documented adjustable highpass_hz=1500
        res = evaluate_detection(dark_audio, self.times, self.gt, highpass_hz=1500.0)
        self.assertEqual(res["onset_recall"], 1.0)
        self.assertEqual(res["onset_precision"], 1.0)
        self.assertEqual(res["onset_fp"], 0)
        self.assertEqual(res["hesitation_recall"], 1.0)
        self.assertEqual(res["spurious_hesitations"], 0)
        self.assertLessEqual(res["hesitation_timing_error_ms"], 30.0)

    def test_dark_pickup_with_default_3000hz_highpass(self):
        """Condition (e2): 2 kHz low-pass evaluated under default highpass_hz=3000."""
        sos_lp = butter(4, 2000.0, btype="lowpass", fs=SR, output="sos")
        dark_audio = sosfilt(sos_lp, self.audio.astype(np.float64)).astype(np.float32)

        # Evaluated under default 3 kHz cutoff
        res = evaluate_detection(dark_audio, self.times, self.gt, highpass_hz=3000.0)
        self.assertEqual(res["onset_recall"], 1.0)
        self.assertEqual(res["onset_precision"], 1.0)
        self.assertEqual(res["onset_fp"], 0)
        self.assertEqual(res["hesitation_recall"], 1.0)

    def test_quiet_input_peaking_at_minus_30_dbfs(self):
        """Condition (f): Quiet input peaking at -30 dBFS (0.0316 peak) detected with 100% recall."""
        peak_target = 10.0 ** (-30.0 / 20.0)  # ~0.03162
        peak_current = float(np.max(np.abs(self.audio)))
        quiet_audio = (self.audio * (peak_target / peak_current)).astype(np.float32)

        res = evaluate_detection(quiet_audio, self.times, self.gt)
        self.assertEqual(res["onset_recall"], 1.0, "All 16 onsets detected on quiet input")
        self.assertEqual(res["onset_precision"], 1.0)
        self.assertEqual(res["onset_fp"], 0)
        self.assertEqual(res["hesitation_recall"], 1.0)
        self.assertEqual(res["spurious_hesitations"], 0)
        self.assertLessEqual(res["hesitation_timing_error_ms"], 30.0)

    @unittest.expectedFailure
    def test_extreme_sub_threshold_silence_rejection(self):
        """Condition (f2) KNOWN LIMIT: Input peaking below -85 dBFS drops below 1e-9 silence cutoff.

        Known limit: Inputs peaking at or below -85 dBFS fall below the 1e-9 energy silence
        threshold in detect_onsets and are rejected as silent (0 onsets detected).
        """
        peak_target = 10.0 ** (-85.0 / 20.0)  # ~0.000056 (-85 dBFS)
        peak_current = float(np.max(np.abs(self.audio)))
        sub_threshold_audio = (self.audio * (peak_target / peak_current)).astype(np.float32)

        res = evaluate_detection(sub_threshold_audio, self.times, self.gt)
        # Expected to fail: signal falls below the hardcoded 1e-9 energy floor in detect_onsets
        self.assertEqual(
            res["onset_recall"],
            1.0,
            "Expected failure: signal at -85 dBFS triggers silence threshold (0 onsets)",
        )

    def test_pure_hum_and_noise_contain_zero_spurious_onsets(self):
        """Pure mains hum and noise without guitar produce 0 false-positive onsets."""
        t_vec = np.arange(3 * SR) / SR
        pure_hum = (0.03162 * np.sin(2.0 * np.pi * 60.0 * t_vec)).astype(np.float32)
        onsets_hum = detect_onsets(pure_hum, SR)
        self.assertEqual(len(onsets_hum), 0, "Mains hum alone must produce 0 onsets")

        rng = np.random.default_rng(777)
        pure_noise = rng.normal(0.0, 0.010, 3 * SR).astype(np.float32)
        onsets_noise = detect_onsets(pure_noise, SR)
        self.assertEqual(len(onsets_noise), 0, "White noise alone must produce 0 onsets")

    def test_e2e_disk_takereport_pipeline_under_degradation(self):
        """End-to-end analyze_take from disk on degraded DI take."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            wav_path = tmp_path / "take-di-degraded.wav"
            sidecar_path = tmp_path / "take-di-degraded.json"

            # Combine hum (-30 dBFS) + noise (-45 dBFS) + DC offset (+0.02)
            t_vec = np.arange(len(self.audio)) / SR
            hum = (0.03162 * np.sin(2.0 * np.pi * 60.0 * t_vec)).astype(np.float32)
            rng = np.random.default_rng(42)
            noise = rng.normal(0.0, 10.0 ** (-45.0 / 20.0), len(self.audio)).astype(np.float32)
            combined = self.audio + hum + noise + 0.02

            write_wav(wav_path, combined, SR)
            sidecar_data = {
                "version": 1,
                "take_id": "take-di-degraded",
                "wav": wav_path.name,
                "samplerate": SR,
                "frames": len(combined),
                "seconds": round(len(combined) / SR, 4),
                "started_unix_ms": 1700200000000,
                "source": "di_hardware_simulation",
            }
            sidecar_path.write_text(json.dumps(sidecar_data, indent=2))

            report = analyze_take(wav_path, sidecar_path)
            self.assertEqual(report.take_id, "take-di-degraded")
            self.assertEqual(report.strum_count, 16)
            self.assertTrue(report.judgeable)
            self.assertAlmostEqual(report.strum_rate_per_min, 120.0, delta=4.0)

            hes = [f for f in report.findings if f["type"] == "hesitation"]
            self.assertEqual(len(hes), 1)
            self.assertAlmostEqual(hes[0]["at_ms"], self.gt["recovery_time_ms"], delta=30.0)


if __name__ == "__main__":
    unittest.main()
