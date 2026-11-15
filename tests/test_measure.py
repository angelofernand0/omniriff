"""tools.measure with injected hardware: no audio devices, no real time."""
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio import Engine  # noqa: E402
from engine.check import FAIL, PASS, Row  # noqa: E402
from tools.measure import core  # noqa: E402
from tools.measure.__main__ import parser  # noqa: E402

NOW = datetime(2026, 11, 15, 1, 0, 0, tzinfo=timezone.utc)


def args(tmp, **kw):
    a = parser().parse_args(["--in", "Focusrite", "--out", "Focusrite", "--hostapi", "WASAPI",
                             "--out-dir", str(tmp), "--soak-minutes", "0"])
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def fake_loopback(ns):
    assert ns.blocksize == 128 and ns.hostapi == "WASAPI" and ns.input_channel == 2
    return dict(clicks=20, detected=20, median_ms=11.2, min_ms=10.9, max_ms=11.6, stdev_ms=0.2,
                mode="loopback", blocksize=128, xruns=0)


def fake_cpu(blocksizes, samplerate):
    return [dict(blocksize=blocksizes[0], budget_ms=2.667, mean_ms=0.25, p99_ms=0.4, max_ms=1.0, load_pct_mean=9.4)]


def ok_checks(input_channel):
    return [Row("audio Focusrite device", PASS, "Focusrite USB")]


class MeasureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_measure(self, a, steps):
        out = core.run(a, ["--test"], steps=steps, now=NOW)
        return out, json.loads((out / "results.json").read_text()), (out / "results.md").read_text()

    def test_all_measured_numbers_reach_the_markdown(self):
        out, results, md = self.run_measure(args(self.dir), {
            "check": dict(run_checks=ok_checks), "latency": dict(loopback=fake_loopback),
            "cpu": dict(time_engine=fake_cpu)})
        self.assertEqual(out.name, "20261115T010000Z")
        self.assertEqual(results["steps"]["latency"]["status"], "pass")
        self.assertIn("11.2 ms median (spread 10.9–11.6 ms) at 128-sample blocks, WASAPI", md)
        self.assertIn("20/20 clicks", md)
        self.assertIn("0.25 ms mean", md)
        self.assertIn("Dropouts over a play test: not measured", md)
        self.assertIn("Ears on a real take: not measured", md)
        self.assertEqual(results["settings"]["input"], "Focusrite")

    def test_failed_or_skipped_steps_never_invent_numbers(self):
        def no_device(ns):
            raise SystemExit("No input device matches name='Focusrite'")  # what resolve_device does
        def bad_checks(input_channel):
            return [Row("audio Focusrite device", FAIL, "not found")]
        a = args(self.dir, skip_cpu=True)
        _, results, md = self.run_measure(a, {"check": dict(run_checks=bad_checks),
                                              "latency": dict(loopback=no_device)})
        self.assertEqual(results["steps"]["check"]["status"], "fail")
        self.assertEqual(results["steps"]["latency"]["status"], "fail")
        self.assertIn("Focusrite", results["steps"]["latency"]["error"])
        self.assertEqual(results["steps"]["cpu"]["status"], "skipped")
        self.assertIn("Guitar-to-output latency: not measured", md)
        self.assertIn("Engine CPU per block: not measured", md)
        self.assertIn("preflight FAIL rows: audio Focusrite device", md)
        self.assertNotIn(" ms median", md)

    def test_undetected_clicks_fail_the_latency_step(self):
        def silent(ns):
            return dict(clicks=20, detected=0, warning="Most clicks were not detected")
        a = args(self.dir, skip_check=True, skip_cpu=True)
        _, results, md = self.run_measure(a, {"latency": dict(loopback=silent)})
        self.assertEqual(results["steps"]["latency"]["status"], "fail")
        self.assertIn("latency: not measured", md)

    def test_refuses_to_overwrite_a_results_folder(self):
        a = args(self.dir, skip_check=True, skip_latency=True, skip_cpu=True)
        core.run(a, [], now=NOW)
        with self.assertRaises(FileExistsError):
            core.run(a, [], now=NOW)

    def test_soak_reads_the_engines_xrun_counters(self):
        engine = Engine()
        def run_live(e, i, o, ch, outs, bs, lat, ex, stop):
            buf = np.zeros((bs, 2), np.float32)
            for _ in range(10):
                e.process(np.zeros(bs, np.float32), buf)
            e.note_xrun()
            stop.wait(5)
            return {"latency_s": (0.005, 0.006), "samplerate": 48000.0, "blocksize": bs}
        a = Namespace(in_dev="Focusrite", out_dev="Focusrite", hostapi="WASAPI", input_channel=2,
                      blocksize=128, latency="low", exclusive=False, soak_minutes=0.0001)
        data = core.step_soak(a, run_live=run_live, resolve=lambda *x: 1,
                              engine_factory=lambda: engine, sleep=lambda s: None)
        self.assertEqual(data["xruns"], 1)
        self.assertEqual(data["blocks"], 10)
        self.assertEqual(data["stream"]["latency_s"], [0.005, 0.006])

    def test_soak_surfaces_a_stream_error(self):
        def broken(*a):
            raise OSError("device unavailable")
        a = Namespace(in_dev=None, out_dev=None, hostapi=None, input_channel=2, blocksize=128,
                      latency="low", exclusive=False, soak_minutes=0.01, samplerate=48000)
        with self.assertRaisesRegex(RuntimeError, "device unavailable"):
            core.step_soak(a, run_live=broken, resolve=lambda *x: None, engine_factory=Engine,
                           sleep=lambda s: None)

    def test_take_is_recorded_and_analyzed_by_ears(self):
        sr = 48000
        rng = np.random.default_rng(1)
        audio = np.zeros(sr * 4, np.float32)
        for k in range(8):  # 8 sharp broadband attacks, 0.5 s apart
            start = int((0.25 + 0.5 * k) * sr)
            n = int(0.05 * sr)
            audio[start:start + n] += (rng.standard_normal(n) * np.exp(-np.arange(n) / 600)).astype(np.float32) * 0.3
        a = Namespace(in_dev="Focusrite", hostapi="WASAPI", input_channel=2, take_seconds=4, samplerate=sr)
        data = core.step_take(a, self.dir, record=lambda *x: audio, resolve=lambda *x: 1)
        self.assertTrue((self.dir / "take.wav").exists())
        self.assertTrue((self.dir / "take-report.json").exists())
        self.assertGreaterEqual(data["strum_count"], 6)
        self.assertTrue(data["judgeable"])


if __name__ == "__main__":
    unittest.main()
