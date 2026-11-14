import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio import Engine, EngineConfig  # noqa: E402
from audio.fileio import read_wav  # noqa: E402
from audio.takes import TakeWriter  # noqa: E402

SR = 48000
BLOCK = 128


def sine(freq, seconds, amp=0.3):
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def run(engine, mono, writer=None):
    out = np.zeros((BLOCK, 2), np.float32)
    for s in range(0, len(mono), BLOCK):
        chunk = mono[s:s + BLOCK]
        engine.process(chunk, out[:len(chunk)])
        if writer:
            writer.poll()


class TakeCaptureTests(unittest.TestCase):
    def test_finished_loop_is_saved_with_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = Engine(EngineConfig(samplerate=SR))
            w = TakeWriter(e, tmp)
            phrase = sine(330, 0.5)
            e.toggle_loop()
            run(e, phrase, w)
            e.toggle_loop()
            run(e, np.zeros(BLOCK * 4, np.float32), w)
            self.assertEqual(len(w.saved), 1)
            data, sr = read_wav(w.saved[0])
            self.assertEqual(sr, SR)
            mid = slice(len(phrase) // 4, 3 * len(phrase) // 4)
            np.testing.assert_allclose(data[:, 0][mid], phrase[mid], atol=2e-4)  # dry, untouched by effects
            meta = json.loads(w.saved[0].with_suffix(".json").read_text())
            self.assertEqual(meta["frames"], len(phrase))
            self.assertEqual(meta["samplerate"], SR)
            self.assertLessEqual(meta["started_unix_ms"], meta["ended_unix_ms"])
            self.assertEqual(meta["signal"], "dry post-gain input (pre-effects)")

    def test_take_overwritten_before_copy_is_skipped_not_corrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = Engine(EngineConfig(samplerate=SR))
            w = TakeWriter(e, tmp)
            e.toggle_loop()
            run(e, sine(330, 0.2))
            e.toggle_loop()          # finish (take 1)
            e.toggle_loop()          # clear
            e.toggle_loop()          # start a new recording before the writer looked
            run(e, sine(440, 0.1))
            self.assertIsNone(w.poll())
            self.assertEqual(w.missed, 1)
            self.assertEqual(w.saved, [])

    def test_background_thread_saves_and_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = Engine(EngineConfig(samplerate=SR))
            w = TakeWriter(e, Path(tmp) / "takes").start()
            e.toggle_loop()
            run(e, sine(220, 0.3))
            e.toggle_loop()
            run(e, np.zeros(BLOCK, np.float32))
            w.stop()
            self.assertEqual(len(w.saved), 1)

    def test_engine_cli_saves_take_during_headless_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([sys.executable, "-m", "engine", "--replay", "engine/demo-controls.jsonl",
                                "--headless", "--no-keyboard", "--duration", "4", "--take-dir", tmp,
                                "--ws-port", "0", "--udp-port", "0"],
                               cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            wavs = sorted(Path(tmp).glob("take-*.wav"))
            self.assertEqual(len(wavs), 1, r.stdout[-500:])
            meta = json.loads(wavs[0].with_suffix(".json").read_text())
            # The script records from 1 s to 3 s of wall time. Headless mode paces blocks with sleeps and
            # runs slower than real time, so only check that a real, non-trivial take was captured.
            self.assertGreater(meta["seconds"], 0.5)
            self.assertLessEqual(abs(meta["frames"] - meta["seconds"] * meta["samplerate"]), 3)  # seconds is rounded


if __name__ == "__main__":
    unittest.main()
