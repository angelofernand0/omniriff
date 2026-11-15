"""tools/launch: the presets build the right commands and dashboard URLs. No process is started."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import launch
from tools.launch.__main__ import PRESETS, build_plan, parse, resolve_replay

PORTS = (8080, 47800, 47801, 47802, 47803)


def plan(*argv, replay_dir=None):
    a = parse(list(argv) + ['--vision', 'off'])
    if replay_dir:
        with patch('tools.launch.__main__.REPLAYS', Path(replay_dir)):
            return build_plan(a, sys.executable, PORTS, None)
    return build_plan(a, sys.executable, PORTS, None)


class PresetTests(unittest.TestCase):
    def test_every_preset_is_documented_and_parses(self):
        for name in PRESETS:
            a = parse([name])
            self.assertEqual((a.source, a.coach), (PRESETS[name]['source'], PRESETS[name]['coach']))

    def test_demo_is_simulated_guitar_with_the_live_coach(self):
        p = plan('demo')
        cmd = ' '.join(p.engine_cmd)
        self.assertIn('--virtual-guitar', cmd)
        self.assertIn('--coach', cmd)
        self.assertIn('coachws=ws://127.0.0.1:47803', p.url)
        self.assertIn('sim=guitar', p.url)            # a simulated guitar says so on screen
        self.assertIsNone(p.coach_cmd)

    def test_rig_is_the_real_guitar_and_not_labelled_simulated(self):
        p = plan('rig')
        self.assertNotIn('--virtual-guitar', p.engine_cmd)
        self.assertNotIn('--headless', p.engine_cmd)
        self.assertNotIn('sim=guitar', p.url)

    def test_fallback_runs_the_scripted_coach_as_a_separate_process_and_never_the_live_one(self):
        p = plan('fallback')
        self.assertNotIn('--coach', p.engine_cmd)
        self.assertEqual(p.coach_cmd[1:4], ['-m', 'tools.sim', 'coach'])
        self.assertIn('--engine-ws', p.coach_cmd)
        self.assertIn('coachws=ws://127.0.0.1:47803', p.url)

    def test_replay_needs_no_coach_process_and_points_the_page_at_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'a.jsonl').write_text('x\n')
            p = plan('replay', replay_dir=d)
        self.assertNotIn('--coach', p.engine_cmd)
        self.assertIsNone(p.coach_cmd)
        self.assertIn('replay=replays/a.jsonl', p.url)
        self.assertNotIn('coachws', p.url)

    def test_quiet_turns_the_coach_column_off(self):
        self.assertIn('coach=off', plan('quiet').url)

    def test_hand_feed_is_switched_off_in_the_url_when_there_is_no_vision(self):
        self.assertIn('hand=off', plan('demo').url)

    def test_overrides_beat_the_preset(self):
        p = plan('demo', '--source', 'silent', '--coach', 'off')
        self.assertIn('--headless', p.engine_cmd)
        self.assertNotIn('--coach', p.engine_cmd)

    def test_raw_audio_arguments_replace_the_source_and_drop_the_simulated_label(self):
        p = plan('rig', '--audio', '--in Scarlett --out Scarlett --input-channel 2')
        self.assertIn('--in', p.engine_cmd)
        self.assertNotIn('sim=guitar', p.url)


class ReplayFileTests(unittest.TestCase):
    def test_newest_recording_is_the_default_and_none_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('tools.launch.__main__.REPLAYS', Path(d)):
                with self.assertRaises(SystemExit):
                    resolve_replay(None)
                (Path(d) / 'old.jsonl').write_text('x\n')
                new = Path(d) / 'new.jsonl'
                new.write_text('x\n')
                import os
                os.utime(Path(d) / 'old.jsonl', (1, 1))
                self.assertEqual(resolve_replay(None).name, 'new.jsonl')

    def test_a_file_from_elsewhere_is_copied_in_and_a_missing_one_is_an_error(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as src:
            f = Path(src) / 'mine.jsonl'
            f.write_text('x\n')
            with patch('tools.launch.__main__.REPLAYS', Path(d) / 'replays'):
                self.assertEqual(resolve_replay(str(f)).name, 'mine.jsonl')
                self.assertTrue((Path(d) / 'replays' / 'mine.jsonl').is_file())
                with self.assertRaises(SystemExit):
                    resolve_replay(str(Path(src) / 'nope.jsonl'))


if __name__ == '__main__':
    unittest.main()
