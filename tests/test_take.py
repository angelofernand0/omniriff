import tempfile
from pathlib import Path
import unittest
from engine.replay import Replay
from vision.take import TakeRecorder
from vision.scenes import SceneMorph, SCENES


class TakeTests(unittest.TestCase):
    def test_scene_take_loads_in_engine_replay_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'take.jsonl'
            recorder = TakeRecorder(path)
            morph = SceneMorph(SCENES['bloom'])
            try:
                for i in range(11):
                    for event in morph.events(dict(version=1, source='vision', seq=i,
                            timestamp_ms=0, type='parameter', control='filter', value=i/10, confidence=.9)):
                        self.assertTrue(recorder.record(event))
            finally:
                recorder.close()
            self.assertIsNone(recorder.error)
            replay = Replay.load(path)
            self.assertEqual(len(replay.entries), 22)
            self.assertEqual(replay.entries[-1][1]['control'], 'reverb')
            with self.assertRaises(FileExistsError):
                TakeRecorder(path)
