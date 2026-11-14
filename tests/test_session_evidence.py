import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from audio.takes import write_take
from coach.fixtures.generate import generate
from vision.session_evidence import build,main,select_takes


class SessionEvidenceTests(unittest.TestCase):
    def take(self,root,name,start):
        wav=root/f'{name}.wav'
        write_take(wav,np.zeros(8000,np.float32),8000,start,source='synthetic_test')
        return wav

    def test_bounded_selection_and_chronological_cards_preserve_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);takes=root/'takes';takes.mkdir()
            paths=[self.take(takes,name,start) for name,start in [('a',105000),('b',103000),('c',101000)]]
            original={p.name:p.read_bytes() for p in paths}
            result=build(takes,root/'view',label='<script>TEST</script>',limit=2,metadata_only=True)
            self.assertEqual(result['selected'],2)
            self.assertEqual([item['take_id'] for item in result['takes']],['c','b'])
            self.assertEqual(result['errors'],[])
            self.assertTrue(all(not row['judgeable'] and not row['hand_available'] for row in result['takes']))
            self.assertTrue(all(not (root/'view'/row['folder']/'take.wav').exists() for row in result['takes']))
            html=(root/'view/index.html').read_text()
            self.assertIn('&lt;script&gt;TEST&lt;/script&gt;',html)
            self.assertNotIn('<script>TEST</script>',html)
            for p in paths:self.assertEqual(p.read_bytes(),original[p.name])

    def test_bad_take_is_listed_and_valid_replay_survives_with_nonzero_cli_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);takes=root/'takes';takes.mkdir()
            self.take(takes,'good',100000)
            (takes/'unfinished.wav').write_bytes(b'incomplete')
            output=root/'view'
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as error:
                main([str(takes),'--label','SYNTHETIC MIXED SESSION','--output',str(output)])
            self.assertEqual(error.exception.code,2)
            result=json.loads((output/'session.json').read_text())
            self.assertEqual(len(result['takes']),1)
            self.assertEqual(len(result['errors']),1)
            self.assertEqual(result['errors'][0]['file'],'unfinished.wav')
            self.assertNotIn(str(root),result['errors'][0]['error'])
            self.assertIn('EXPORT FINISHED WITH REJECTED FILES',(output/'index.html').read_text())
            self.assertTrue((output/result['takes'][0]['folder']/'take.wav').exists())

    def test_duplicate_identity_cannot_overwrite_an_earlier_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);takes=root/'takes';takes.mkdir()
            first=self.take(takes,'a',100000);second=self.take(takes,'b',102000)
            meta=json.loads(second.with_suffix('.json').read_text());meta['take_id']='a';second.with_suffix('.json').write_text(json.dumps(meta))
            result=build(takes,root/'view',label='SYNTHETIC DUPLICATE')
            self.assertEqual(len(result['takes']),1)
            self.assertEqual(result['takes'][0]['take_id'],'a')
            self.assertIn('duplicate',result['errors'][0]['error'])
            self.assertEqual((root/'view/take-001/take.wav').read_bytes(),first.read_bytes())

    def test_preflight_folder_log_bounds_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);takes=root/'takes';takes.mkdir();self.take(takes,'a',100000)
            with self.assertRaises(ValueError):build(takes,root/'missing-log',label='TEST',hand_log=root/'absent.jsonl')
            self.assertFalse((root/'missing-log').exists())
            with patch('vision.session_evidence.MAX_DIRECTORY_ENTRIES',0),self.assertRaises(ValueError):select_takes(takes,20)
            with self.assertRaises(ValueError):select_takes(takes,101)
            output=root/'existing';output.mkdir();(output/'keep').write_text('keep')
            with patch('vision.session_evidence.analyze_capture') as analyze,self.assertRaises(FileExistsError):build(takes,output,label='TEST')
            analyze.assert_not_called()
            self.assertEqual((output/'keep').read_text(),'keep')

    def test_interruption_preserves_completed_pages_with_incomplete_manifest(self):
        from vision.evidence import analyze_capture
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);takes=root/'takes';takes.mkdir();self.take(takes,'a',100000);self.take(takes,'b',102000)
            def analyze(path,**kwargs):
                if path.stem=='b':raise KeyboardInterrupt()
                return analyze_capture(path,**kwargs)
            with patch('vision.session_evidence.analyze_capture',side_effect=analyze),self.assertRaises(KeyboardInterrupt):
                build(takes,root/'view',label='SYNTHETIC INTERRUPTED SESSION')
            result=json.loads((root/'view/session.json').read_text())
            self.assertFalse(result['complete'])
            self.assertEqual(len(result['takes']),1)
            self.assertTrue((root/'view/take-001/index.html').exists())
            self.assertIn('EXPORT INCOMPLETE',(root/'view/index.html').read_text())

    def test_aggregate_audio_copy_budget_applies_before_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);takes=root/'takes';takes.mkdir();self.take(takes,'a',100000)
            with patch('vision.session_evidence.MAX_COPIED_AUDIO_BYTES',1),self.assertRaises(ValueError):
                build(takes,root/'view',label='TEST')
            self.assertFalse((root/'view').exists())
            with patch('vision.session_evidence.MAX_COPIED_AUDIO_BYTES',1):
                result=build(takes,root/'metadata',label='TEST',metadata_only=True)
            self.assertTrue(result['complete'])

    def test_real_analyzers_align_three_fixture_takes_from_one_session_log(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);takes=root/'takes';manifest=generate(takes,16000)
            by_id={row['take_id']:row for row in manifest['takes']};log=root/'session.jsonl';rows=[]
            for i,name in enumerate(['coach-before','coach-clean','coach-after']):
                item=by_id[name];path=takes/item['sidecar'];meta=json.loads(path.read_text());offset=i*20000
                meta['started_unix_ms']+=offset;meta['ended_unix_ms']+=offset;path.write_text(json.dumps(meta))
                for line in (takes/item['hand_log']).read_text().splitlines():
                    row=json.loads(line);row['timestamp_ms']+=offset;rows.append(row)
            log.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            output=root/'view';result=build(takes,output,label='SYNTHETIC SESSION FIXTURE',hand_log=log)
            self.assertEqual(result['errors'],[])
            self.assertEqual([r['take_id'] for r in result['takes']],['coach-before','coach-clean','coach-after'])
            reports=[json.loads((output/r['folder']/'evidence.json').read_text()) for r in result['takes']]
            self.assertEqual([len(r['ears']['findings']) for r in reports],[3,0,3])
            self.assertEqual([len(r['hands']['stalls']) for r in reports],[3,0,0])
            self.assertTrue(all(r['hands']['available'] for r in reports))
            self.assertGreater(result['takes'][0]['longest_extra_ms'],result['takes'][2]['longest_extra_ms'])

    def test_truncated_fmt_header_is_rejected_without_aborting_other_takes(self):
        import struct
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);takes=root/'takes';takes.mkdir();wav=self.take(takes,'a',100000);self.take(takes,'b',102000)
            wav.write_bytes(b'RIFF'+struct.pack('<I',100)+b'WAVEfmt '+struct.pack('<I',16)+b'\x01\x00')
            result=build(takes,root/'view',label='SYNTHETIC TRUNCATION TEST')
            self.assertTrue(result['complete'])
            self.assertEqual([row['take_id'] for row in result['takes']],['b'])
            self.assertEqual(len(result['errors']),1)
            self.assertIn('header is truncated',result['errors'][0]['error'])
