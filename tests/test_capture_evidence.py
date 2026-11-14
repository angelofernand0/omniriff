"""One-command replay export uses production analyzers and strict capture metadata."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from audio.takes import write_take
from coach.fixtures.generate import generate
from vision.evidence import analyze_capture, main


class CaptureEvidenceTests(unittest.TestCase):
    def silent_take(self, root):
        wav=root/'silent.wav'
        write_take(wav,np.zeros(16000,np.float32),16000,100000,source='synthetic_test')
        return wav

    def test_actual_fixture_single_command_retains_aligned_findings_and_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);fixtures=root/'fixtures';manifest=generate(fixtures,16000)
            row=next(r for r in manifest['takes'] if r['take_id']=='coach-before')
            wav=fixtures/row['wav'];log=fixtures/row['hand_log'];output=root/'view'
            with contextlib.redirect_stdout(io.StringIO()):
                main(['--take',str(wav),'--hand-log',str(log),'--output',str(output),'--label','SYNTHETIC FIXTURE'])
            evidence=json.loads((output/'evidence.json').read_text())
            self.assertTrue(evidence['ears']['judgeable'])
            self.assertTrue(evidence['hands']['available'])
            self.assertEqual(len(evidence['ears']['findings']),3)
            self.assertEqual(len(evidence['hands']['stalls']),3)
            self.assertEqual(evidence['ears']['started_unix_ms'],evidence['hands']['started_unix_ms'])
            self.assertEqual((output/'take.wav').read_bytes(),wav.read_bytes())

    def test_audio_only_and_empty_log_remain_unavailable_and_unjudgeable(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);wav=self.silent_take(root);log=root/'empty.jsonl';log.touch()
            for hand_log in (None,log):
                ears,hands=analyze_capture(wav,hand_log=hand_log)
                self.assertFalse(ears['judgeable'])
                self.assertFalse(hands['available'])
                self.assertEqual(hands['coverage'],0)
                self.assertEqual(hands['stalls'],[])
            with contextlib.redirect_stdout(io.StringIO()):
                main(['--take',str(wav),'--metadata-only','--label','SYNTHETIC SILENCE','--output',str(root/'metadata')])
            self.assertTrue((root/'metadata/index.html').exists())
            self.assertFalse((root/'metadata/take.wav').exists())

    def test_invalid_sidecar_or_wav_is_rejected_before_ears_and_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);wav=self.silent_take(root);sidecar=wav.with_suffix('.json')
            original=json.loads(sidecar.read_text())
            for key,value in [('version',2),('take_id',''),('frames',3),('samplerate',8000),
                              ('seconds',2),('wav','other.wav'),('ended_unix_ms',99999),('started_unix_ms',True)]:
                metadata=copy.deepcopy(original);metadata[key]=value;sidecar.write_text(json.dumps(metadata))
                with patch('tools.ears.analyze.analyze_take') as ears,self.assertRaises(ValueError):
                    analyze_capture(wav)
                ears.assert_not_called()
            sidecar.write_text(json.dumps(original))
            wav.write_bytes(wav.read_bytes()[:-100])
            with patch('tools.ears.analyze.analyze_take') as ears,self.assertRaises(ValueError):
                analyze_capture(wav)
            ears.assert_not_called()
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                main(['--take',str(wav),'--label','BAD PAYLOAD','--output',str(root/'bad-output')])
            self.assertFalse((root/'bad-output').exists())

    def test_analysis_bounds_and_missing_supplied_log_fail_before_ears(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);wav=self.silent_take(root)
            with patch('vision.evidence.MAX_ANALYSIS_SAMPLES',10),patch('tools.ears.analyze.analyze_take') as ears,self.assertRaises(ValueError):
                analyze_capture(wav)
            ears.assert_not_called()
            with patch('tools.ears.analyze.analyze_take') as ears,self.assertRaises(FileNotFoundError):
                analyze_capture(wav,hand_log=root/'missing.jsonl')
            ears.assert_not_called()

    def test_existing_output_refuses_before_any_analysis(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'existing';output.mkdir();(output/'keep.txt').write_text('keep')
            with patch('vision.evidence.analyze_capture') as analyze,contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                main(['--take',str(root/'not-read.wav'),'--label','TEST','--output',str(output)])
            analyze.assert_not_called()
            self.assertEqual((output/'keep.txt').read_text(),'keep')

    def test_compatible_wall_clock_window_offset_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);wav=self.silent_take(root);sidecar=wav.with_suffix('.json')
            meta=json.loads(sidecar.read_text());meta['ended_unix_ms']+=50;sidecar.write_text(json.dumps(meta))
            rows=[dict(timestamp_ms=100000+round(i*1000/30),hands=[dict(handedness='Right',wrist=[.5,.5],confidence=.95)]) for i in range(32)]
            log=root/'hands.jsonl';log.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            ears,hands=analyze_capture(wav,hand_log=log)
            self.assertEqual(ears['duration_s'],1.)
            self.assertEqual(hands['duration_s'],1.05)
            self.assertTrue(hands['available'])
            self.assertGreater(hands['stalls'][0]['end_ms'],1000)

    def test_production_engine_takewriter_sidecar_is_accepted(self):
        from audio import Engine,EngineConfig
        from audio.fileio import read_wav
        from audio.offline import render
        from audio.takes import TakeWriter
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);fixtures=root/'fixtures';manifest=generate(fixtures,16000)
            item=next(r for r in manifest['takes'] if r['take_id']=='coach-before')
            mono,rate=read_wav(fixtures/item['wav']);mono=mono[:,0]
            metadata=json.loads((fixtures/item['sidecar']).read_text())
            started=metadata['started_unix_ms']/1000
            ended=started+len(mono)/rate
            engine=Engine(EngineConfig(samplerate=rate));writer=TakeWriter(engine,root/'takes')
            writer.directory.mkdir()
            with patch('audio.looper.time.time',side_effect=[started,ended]):
                engine.toggle_loop();render(engine,mono)
                engine.toggle_loop();render(engine,np.zeros(128,np.float32))
            captured=writer.poll()
            self.assertIsNotNone(captured)
            ears,hands=analyze_capture(captured,hand_log=fixtures/item['hand_log'])
            self.assertTrue(ears['judgeable'])
            self.assertTrue(hands['available'])
            self.assertEqual(len(ears['findings']),3)
            self.assertEqual(len(hands['stalls']),3)
            self.assertEqual(ears['take_id'],captured.stem)
