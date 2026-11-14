import json
import contextlib
import io
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from vision.hand_log import HandLog,hand_record
from vision.hand_window import report_for_window
from vision.eyes import generate_synthetic_strum_take


class HandWindowTests(unittest.TestCase):
    def write(self,root,rows):
        path=root/'hands.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in rows));return path

    def rows(self):
        start=100000
        rows=[]
        for t,x,y in generate_synthetic_strum_take(6,40,120,2.5,.4):
            rows.append(dict(timestamp_ms=start+round(t*1000),strum_hand='Right',hands=[
                dict(handedness='Left',wrist=[.3,.3],confidence=.99),
                dict(handedness='Right',wrist=[x,y],confidence=.99)]))
        return rows

    def test_exact_take_window_and_stall_alignment_ignore_other_hand(self):
        with tempfile.TemporaryDirectory() as folder:
            path=self.write(Path(folder),self.rows())
            report=report_for_window(path,101000,105000,'take-42')
            self.assertTrue(report['available'])
            self.assertEqual(report['take_id'],'take-42')
            self.assertEqual(report['started_unix_ms'],101000)
            self.assertEqual(len(report['stalls']),1)
            stall=report['stalls'][0]
            self.assertAlmostEqual(stall['start_ms'],1500,delta=40)
            self.assertAlmostEqual(stall['end_ms'],1900,delta=40)
            self.assertEqual(report['selected_hand'],'Right')
            self.assertGreater(report['coverage'],.95)

    def test_missing_or_low_confidence_frames_are_not_stalls(self):
        for missing in (True,False):
            rows=self.rows()
            for row in rows:
                if 102300<=row['timestamp_ms']<=103100:
                    if missing:row['hands']=[]
                    else:row['hands'][1]['confidence']=.1
            with tempfile.TemporaryDirectory() as folder:
                report=report_for_window(self.write(Path(folder),rows),100000,106000,'gap')
                self.assertEqual(report['stalls'],[])
                self.assertGreater(report['tracking_gaps'],0)
                self.assertLess(report['coverage'],1)

    def test_left_selection_duplicate_labels_and_sparse_data(self):
        rows=self.rows()
        for row in rows:
            row['strum_hand']='Left'
            row['hands'][0],row['hands'][1]=row['hands'][1],row['hands'][0]
            row['hands'][0]['handedness']='Left';row['hands'][1]['handedness']='Right'
        with tempfile.TemporaryDirectory() as folder:
            report=report_for_window(self.write(Path(folder),rows),100000,106000,'left')
            self.assertEqual(report['selected_hand'],'Left')
            self.assertEqual(len(report['stalls']),1)
            for row in rows:row['hands'][1]['handedness']='Left'
            report=report_for_window(self.write(Path(folder),rows),100000,106000,'ambiguous')
            self.assertFalse(report['available'])
            self.assertEqual(report['stalls'],[])

    def test_append_writer_flushes_both_wrists_while_capture_runs(self):
        result=NS(hand_landmarks=[[NS(x=.2,y=.4)],[NS(x=.7,y=.6)]],handedness=[
            [NS(category_name='Left',score=.9)],[NS(category_name='Right',score=.95)]])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'live.jsonl'
            logger=HandLog(path)
            try:
                self.assertTrue(logger.record(hand_record(result,1000)))
                for _ in range(100):
                    if path.stat().st_size:break
                    time.sleep(.01)
                first=json.loads(path.read_text())
                self.assertEqual(len(first['hands']),2)
            finally:logger.close()
            second=HandLog(path)
            second.record(hand_record(result,2000,'Left'));second.close()
            self.assertEqual(len(path.read_text().splitlines()),2)
            self.assertIsNone(second.error)

    def test_partial_line_and_invalid_window(self):
        with tempfile.TemporaryDirectory() as folder:
            path=self.write(Path(folder),self.rows())
            with path.open('a') as file:file.write('{"timestamp_ms":')
            report=report_for_window(path,100000,106000,'partial')
            self.assertTrue(report['available'])
            with self.assertRaises(ValueError):HandLog(path)
            with self.assertRaises(ValueError):report_for_window(path,2000,1000,'bad')

    def test_long_camera_gap_and_reordered_rows_cannot_create_freeze(self):
        rows=[]
        for offset in (0,25,50,75,100,1000,1025,1050,1075,1100):
            rows.append(dict(timestamp_ms=100000+offset,hands=[dict(handedness='Right',wrist=[.5,.5],confidence=.9)]))
        rows.append(rows[-2])
        with tempfile.TemporaryDirectory() as folder:
            report=report_for_window(self.write(Path(folder),rows),100000,101200,'gap')
            self.assertFalse(report['available'])
            self.assertEqual(report['stalls'],[])
            self.assertGreater(report['tracking_gaps'],0)
            self.assertGreater(report['rejected_rows'],0)

    def test_logger_bounds_stop_capture_log_without_truncating_history(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bounded.jsonl'
            logger=HandLog(path)
            try:
                self.assertTrue(logger.record(dict(timestamp_ms=1000,hands=[])))
                with patch('vision.hand_log.MAX_BYTES',logger.size):
                    self.assertFalse(logger.record(dict(timestamp_ms=2000,hands=[])))
                self.assertIsNotNone(logger.error)
            finally:logger.close()
            self.assertEqual(len(path.read_text().splitlines()),1)

    def test_hand_record_drops_nonfinite_or_offscreen_wrist(self):
        result=NS(hand_landmarks=[[NS(x=float('nan'),y=.4)],[NS(x=1.2,y=.4)]],handedness=[
            [NS(category_name='Left',score=.9)],[NS(category_name='Right',score=.95)]])
        self.assertEqual(hand_record(result,1000)['hands'],[])

    def test_cli_uses_sidecar_and_refuses_overwrite(self):
        from vision.hand_window import main
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=self.write(root,self.rows())
            sidecar=root/'take.json';sidecar.write_text(json.dumps(dict(take_id='clip',started_unix_ms=101000,ended_unix_ms=105000)))
            output=root/'report.json'
            args=[str(path),str(sidecar),'--output',str(output)]
            main(args)
            report=json.loads(output.read_text())
            self.assertEqual(report['take_id'],'clip')
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):main(args)

    def test_malformed_small_rows_cannot_abort_coach_analysis(self):
        with tempfile.TemporaryDirectory() as folder:
            path=self.write(Path(folder),self.rows())
            with path.open('a') as file:
                file.write('['*1200+'0'+']'*1200+'\n')
                file.write('{"timestamp_ms":105999,"hands":[{"handedness":"Right","wrist":['+'9'*1000+',0.5],"confidence":0.9}]}\n')
            report=report_for_window(path,100000,106000,'malformed')
            self.assertGreaterEqual(report['rejected_rows'],2)
            self.assertTrue(report['available'])

    def test_existing_coach_runner_resolves_public_api(self):
        from coach.runner import hand_report
        with tempfile.TemporaryDirectory() as folder:
            path=self.write(Path(folder),self.rows())
            sidecar=dict(take_id='real-mode-fixture',started_unix_ms=100000,ended_unix_ms=106000)
            result=hand_report(path,sidecar,fixture_mode=False)
            self.assertTrue(result['available'])
            self.assertEqual(result['take_id'],sidecar['take_id'])
            self.assertEqual(len(result['stalls']),1)
            self.assertEqual(result['source'],'vision.eyes/window')

    def test_discarded_short_segments_cannot_supply_available_coverage(self):
        times=[0,40,80,120,160]
        for start in range(350,3500,600):times.extend(start+delta for delta in (0,140,280,420))
        rows=[dict(timestamp_ms=100000+t,hands=[dict(handedness='Right',wrist=[.5,.5],confidence=.9)]) for t in times]
        with tempfile.TemporaryDirectory() as folder:
            report=report_for_window(self.write(Path(folder),rows),100000,104000,'fragmented')
            self.assertFalse(report['available'])
            self.assertGreater(report['observed_coverage'],.5)
            self.assertLess(report['coverage'],.1)
            self.assertEqual(report['motion_continuity_score'],0)

    def test_window_sample_limit_is_enforced(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            path=self.write(Path(folder),self.rows())
            with patch('vision.hand_window.MAX_WINDOW_SAMPLES',2),self.assertRaises(ValueError):
                report_for_window(path,100000,106000,'bounded')
