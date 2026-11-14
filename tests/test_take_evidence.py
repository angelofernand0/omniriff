import copy
import json
from pathlib import Path
import tempfile
import unittest
import wave
from vision.evidence import export,validate


class TakeEvidenceTests(unittest.TestCase):
    def reports(self):
        ears=dict(take_id='take-1',started_unix_ms=100000,duration_s=2.,findings=[dict(at_ms=1200,extra_ms=300,message='Pause <script>bad()</script>')])
        hands=dict(take_id='take-1',started_unix_ms=100000,duration_s=2.,available=True,coverage=.9,stalls=[dict(start_ms=900,end_ms=1200,message='Observed pause')])
        return ears,hands

    def test_matching_reports_export_portable_page_audio_and_escaped_payload(self):
        ears,hands=self.reports()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);wav=root/'source.wav'
            with wave.open(str(wav),'wb') as writer:
                writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(8000);writer.writeframes(b'\x00\x00'*16000)
            page=export(ears,hands,root/'result',label='SYNTHETIC TEST',audio=wav)
            self.assertTrue(page.exists())
            html=page.read_text()
            self.assertIn('take.wav',html)
            self.assertNotIn('<script>bad()</script>',html)
            self.assertIn('\\u003cscript>',html)
            self.assertEqual((root/'result/take.wav').read_bytes(),wav.read_bytes())
            self.assertEqual(json.loads((root/'result/evidence.json').read_text())['label'],'SYNTHETIC TEST')
            with self.assertRaises(FileExistsError):export(ears,hands,root/'result',label='test')

    def test_mismatched_take_start_duration_and_invalid_spans_rejected(self):
        ears,hands=self.reports()
        variants=[]
        for key,value in (('take_id','other'),('started_unix_ms',100001),('duration_s',3.)):
            changed=copy.deepcopy(hands);changed[key]=value;variants.append(changed)
        changed=copy.deepcopy(hands);changed['stalls'][0]['end_ms']=800;variants.append(changed)
        changed=copy.deepcopy(hands);changed['stalls'][0]['start_ms']=float('nan');variants.append(changed)
        for changed in variants:
            with self.assertRaises(ValueError):validate(ears,changed)

    def test_incomplete_report_is_preserved_without_audio_or_false_success(self):
        ears,hands=self.reports();hands.update(available=False,coverage=.1)
        with tempfile.TemporaryDirectory() as folder:
            page=export(ears,hands,Path(folder)/'report',label='UNVERIFIED')
            self.assertIn('WRIST EVIDENCE INCOMPLETE',page.read_text())
            self.assertNotIn('id="audio"',page.read_text())
            self.assertFalse((page.parent/'take.wav').exists())

    def test_audio_duration_or_truncated_payload_rejected_before_output(self):
        ears,hands=self.reports()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);wav=root/'source.wav'
            with wave.open(str(wav),'wb') as writer:
                writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(8000);writer.writeframes(b'\x00\x00'*8000)
            with self.assertRaises(ValueError):export(ears,hands,root/'wrong-duration',label='test',audio=wav)
            self.assertFalse((root/'wrong-duration').exists())
            with wave.open(str(wav),'wb') as writer:
                writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(8000);writer.writeframes(b'\x00\x00'*16000)
            wav.write_bytes(wav.read_bytes()[:-1000])
            with self.assertRaises(ValueError):export(ears,hands,root/'truncated',label='test',audio=wav)
            self.assertFalse((root/'truncated').exists())

    def test_cli_loads_saved_reports_and_source_label(self):
        import contextlib
        import io
        from vision.evidence import main
        ears,hands=self.reports()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'ears.json').write_text(json.dumps(ears));(root/'hands.json').write_text(json.dumps(hands))
            with contextlib.redirect_stdout(io.StringIO()):
                main(['--ears',str(root/'ears.json'),'--hands',str(root/'hands.json'),
                      '--label','SYNTHETIC CLI TEST','--output',str(root/'view')])
            self.assertEqual(json.loads((root/'view/evidence.json').read_text())['label'],'SYNTHETIC CLI TEST')

    def test_oversized_numeric_value_rejected_consistently(self):
        ears,hands=self.reports();ears['duration_s']=10**1000
        with self.assertRaises(ValueError):validate(ears,hands)

    def test_accepted_clock_duration_offset_keeps_wrist_window_valid(self):
        ears,hands=self.reports()
        hands['duration_s']=2.05
        hands['stalls'][0].update(start_ms=1800,end_ms=2033)
        self.assertEqual(validate(ears,hands),2.)
        with tempfile.TemporaryDirectory() as folder:
            page=export(ears,hands,Path(folder)/'offset',label='SYNTHETIC CLOCK OFFSET')
            self.assertIn('Wrist-window duration offset',page.read_text())
