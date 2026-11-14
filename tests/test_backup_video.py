"""Hardware-free checks for the labelled backup recorder."""
import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np

from audio import Engine, EngineConfig
from engine.replay import Replay
from tools.backup_video.__main__ import (
    BLOCKSIZE, CONTROLS, LABEL, SAMPLERATE, audio_worker, preflight, validate_duration,
)


class BackupVideoTests(unittest.TestCase):
    def test_duration_covers_replay_and_video_limit(self):
        replay = Replay.load(CONTROLS)
        validate_duration(10, replay)
        for seconds in (0, 7.4, 120.1, float("nan")):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                validate_duration(seconds, replay)

    def test_never_overwrites_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "existing.mp4"
            output.write_bytes(b"keep")
            with self.assertRaisesRegex(ValueError, "already exists"):
                preflight(output, None)
            self.assertEqual(output.read_bytes(), b"keep")

    def test_audio_worker_processes_source_without_audio_device(self):
        source = np.zeros(BLOCKSIZE * 3, np.float32)
        source[0] = 0.5
        output = np.zeros((len(source), 2), np.float32)
        start, abort, done = threading.Event(), threading.Event(), threading.Event()
        errors = []
        start.set()
        audio_worker(Engine(EngineConfig(samplerate=SAMPLERATE)), source, output,
                     start, abort, done, errors)
        self.assertTrue(done.is_set())
        self.assertEqual(errors, [])
        self.assertTrue(np.isfinite(output).all())
        self.assertGreater(np.abs(output).sum(), 0)

    def test_disclosure_is_explicit(self):
        self.assertIn("SIMULATED", LABEL)
        self.assertIn("NO HARDWARE", LABEL)


if __name__ == "__main__":
    unittest.main()
