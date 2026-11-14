import unittest
import contextlib
import io
import json
from pathlib import Path
import tempfile
import numpy as np
from audio.fileio import make_test_signal, write_wav, read_wav
from tools.tone_match.match import effect, fit, validate_pair, residual
from tools.tone_match.__main__ import main
from tools.virtual_guitar.guitar import performance
from engine.replay import Replay
from vision.scenes import SceneMorph


class ToneMatchTests(unittest.TestCase):
    def test_recovers_hidden_parameters_and_exports_scene(self):
        sr = 12000
        dry = make_test_signal(1, sr) * .4
        reference = effect(dry, sr, .43, .37)
        result = fit(dry, reference, sr, seconds=1, evaluations=96)
        self.assertLess(result.residual, .01)
        self.assertLess(result.residual, result.baseline_residual * .05)
        self.assertAlmostEqual(result.filter, .43, delta=.025)
        self.assertAlmostEqual(result.reverb, .37, delta=.06)
        self.assertLessEqual(result.evaluations, 96)
        SceneMorph(result.scene())

    def test_gain_is_comparison_only_and_bounded(self):
        signal = np.array([.1, -.2, .3], np.float32)
        loss, gain = residual(signal, signal * 2)
        self.assertLess(loss, 1e-12)
        self.assertAlmostEqual(gain, 2)

    def test_silence_length_nonfinite_rejected(self):
        good = np.ones(8000, np.float32) * .1
        for bad in (np.zeros(8000), np.full(8000, np.nan), good[:10], np.ones(8000)*2):
            with self.assertRaises(ValueError):
                validate_pair(good, bad, 8000)

    def test_physical_guitar_gain_and_unrelated_performance(self):
        rate = 12000
        dry = performance(1, rate)
        target = effect(dry, rate, .21, .82) * 1.6
        matched = fit(dry, target, rate, evaluations=96, seconds=1)
        self.assertLess(matched.residual, .001)
        self.assertAlmostEqual(matched.reference_gain, 1.6, delta=.03)
        unrelated = fit(dry, performance(1, rate, seed=94), rate, evaluations=24, seconds=1)
        self.assertGreater(unrelated.residual, .25)
        self.assertTrue(unrelated.assessment.startswith('poor fit'))

    def test_cli_exports_audition_and_rejects_overwrite(self):
        rate = 8000
        dry = make_test_signal(1.2, rate) * .3
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_wav(root/'dry.wav', dry, rate)
            write_wav(root/'target.wav', effect(dry, rate, .2, .5), rate)
            args = ['--dry', str(root/'dry.wav'), '--reference', str(root/'target.wav'),
                    '--output', str(root/'match'), '--seconds', '.5', '--evaluations', '24',
                    '--name', '<script>bad</script>']
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                main(args)
                with self.assertRaises(SystemExit) as error:
                    main(args)
            self.assertEqual(error.exception.code, 2)
            scene = json.loads((root/'match/scene.json').read_text())
            SceneMorph(scene)
            replay = Replay.load(root/'match/scripted-morph-controls.jsonl')
            self.assertGreater(len(replay.entries), 10)
            self.assertAlmostEqual(replay.entries[-2][1]['value'], scene['to']['filter'])
            self.assertAlmostEqual(replay.entries[-1][1]['value'], scene['to']['reverb'])
            report = json.loads((root/'match/report.json').read_text())
            self.assertIsNotNone(report['remaining_recording_residual'])
            self.assertLess(report['full_recording_residual'], .001)
            html = (root/'match/index.html').read_text()
            self.assertNotIn('<script>bad</script>', html)
            self.assertIn('&lt;script&gt;bad&lt;/script&gt;', html)
            audio, sr = read_wav(root/'match/audition-baseline-reference-match.wav')
            self.assertEqual(sr, rate)
            self.assertEqual(len(audio), len(dry)*3 + rate)
            self.assertLessEqual(float(np.max(np.abs(audio))), .801)

    def test_analysis_budget_and_pair_mismatch_rejected(self):
        dry = make_test_signal(1, 8000)
        with self.assertRaises(ValueError):
            fit(dry, dry[:-1], 8000)
        for kwargs in ({'evaluations': 23}, {'evaluations': 257}, {'seconds': float('nan')}):
            with self.assertRaises(ValueError):
                fit(dry, dry, 8000, **kwargs)
