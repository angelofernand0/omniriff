"""Measured rehearsal checks never equate replay/no-data with a live pass."""
import contextlib
import io
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import numpy as np
from vision.rehearsal_check import RehearsalCheck
from vision.__main__ import main


HAND=[dict(handedness='Right',wrist=[.5,.4],confidence=.95)]
ZONE_HAND=[dict(handedness='Right',wrist=[.5,.7],confidence=.95)]


class RehearsalCheckTests(unittest.TestCase):
    def test_confirmations_require_a_visible_unambiguous_strum_label(self):
        check=RehearsalCheck(strum_hand='Right',source='webcam',transmission='dry-run',seconds=1)
        check.confirm(ord('c'),0,[])
        check.confirm(ord('z'),0,[])
        self.assertIsNone(check.started)
        check.confirm(ord('c'),0,HAND*2)
        self.assertIsNone(check.started)
        check.confirm(ord('c'),0,HAND)
        check.confirm(ord('z'),0,HAND)
        self.assertIsNone(check.started)
        check.confirm(ord('z'),0,ZONE_HAND)
        self.assertEqual(check.started,0)
        self.assertFalse(check.report()['passed'])

    def run_check(self,source='webcam',expired=False,move=True):
        check=RehearsalCheck(strum_hand='Right',source=source,transmission='dry-run',seconds=1)
        check.confirm(ord('c'),0,HAND);check.confirm(ord('z'),0,ZONE_HAND)
        for i in range(1,11):
            start=i*.1
            check.observe(start,start+.01,[dict(value=i/10 if move else .5)],HAND,expired,control_hand='Right')
            if check.done:break
        return check

    def test_full_moving_measurement_passes_only_webcam_input(self):
        live=self.run_check()
        self.assertTrue(live.report()['passed'])
        self.assertGreater(live.report()['metrics']['processed_fps'],0)
        self.assertGreater(live.report()['metrics']['emitted_events_hz'],0)
        self.assertIn('no audio latency measured',live.summary())
        replay=self.run_check(source='recorded-video')
        self.assertTrue(replay.report()['complete'])
        self.assertFalse(replay.report()['passed'])
        self.assertFalse(replay.report()['checks']['webcam_input'])

    def test_expired_slow_static_or_incomplete_runs_cannot_pass(self):
        for kwargs in (dict(expired=True),dict(move=False)):
            self.assertFalse(self.run_check(**kwargs).report()['passed'])
        check=RehearsalCheck(strum_hand='Right',source='webcam',transmission='udp',seconds=1)
        self.assertIsNone(check.report()['metrics']['processed_fps'])
        self.assertIn('not measured',check.summary())
        self.assertFalse(check.report()['passed'])
        check.confirm(ord('c'),0,HAND);check.confirm(ord('z'),0,ZONE_HAND)
        check.observe(.1,.4,[dict(value=.2)],HAND,False,control_hand='Right')
        check.observe(.5,.8,[dict(value=.8)],HAND,False,control_hand='Right')
        check.observe(.9,1.2,[dict(value=.3)],HAND,False,control_hand='Right')
        self.assertTrue(check.done)
        self.assertFalse(check.report()['checks']['processing_within250ms'])

    def test_actual_main_rehearsal_measures_full_interval_and_exports_check(self):
        clock=[0.];index=[0];drawn=[]
        class Capture:
            def __init__(self,*args):pass
            def isOpened(self):return True
            def get(self,key):return 10
            def read(self):
                index[0]+=1;clock[0]+=.1
                return index[0]<=310,np.zeros((480,640,3),np.uint8)
            def release(self):pass
        class Detector:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def detect_for_video(self,*args):
                y=.65 if index[0]==2 else .4+.05*math.sin(clock[0]*.8)
                pinch=.6 if index[0]%20 in (0,1,2,3) else .1
                hand=[NS(x=.5,y=.5) for _ in range(21)]
                hand[0]=NS(x=.5,y=y);hand[5]=NS(x=.4,y=.5);hand[17]=NS(x=.6,y=.5);hand[8]=NS(x=.5+.2*pinch,y=.5)
                return NS(hand_landmarks=[hand],handedness=[[NS(category_name='Right',score=.95)]])
        cv=NS(VideoCapture=Capture,CAP_PROP_FPS=1,COLOR_BGR2RGB=1,FONT_HERSHEY_SIMPLEX=1,
            cvtColor=lambda frame,mode:frame,destroyAllWindows=lambda:None,circle=lambda *a:None,line=lambda *a:None,
            imshow=lambda *a:None,putText=lambda frame,text,*args:drawn.append(text),
            waitKey=lambda *a:ord('c') if index[0]==1 else ord('z') if index[0]==2 else -1)
        mp=NS(Image=lambda image_format,data:data,ImageFormat=NS(SRGB=1),tasks=NS(BaseOptions=lambda **kw:kw,vision=NS(
            HandLandmarkerOptions=lambda **kw:kw,RunningMode=NS(VIDEO=1),HandLandmarker=NS(create_from_options=lambda options:Detector()))))
        with tempfile.TemporaryDirectory() as folder,patch.dict('sys.modules',{'cv2':cv,'mediapipe':mp}),patch('vision.__main__.time.monotonic',side_effect=lambda:clock[0]),patch('vision.__main__.time.time',side_effect=lambda:1000+clock[0]),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            root=Path(folder);path=root/'metrics.json'
            main(['--model','synthetic.task','--relative','--strum-guard','--rehearsal','--dry-run','--no-hand-view',
                  '--metrics-json',str(path),'--calibration',str(root/'absent.json')])
            report=json.loads(path.read_text())['rehearsal']
            self.assertTrue(report['complete'])
            self.assertTrue(report['passed'])
            self.assertGreaterEqual(report['metrics']['observed_seconds'],30)
            self.assertEqual(report['expired_frames'],0)
            self.assertIn('--rehearsal',report['command'])
            self.assertIn('--model',report['command_line'])
            self.assertTrue(any('Right [STRUM LABEL]' in text for text in drawn))
            self.assertTrue(any('REHEARSAL' in text for text in drawn))

    def test_rehearsal_incompatible_flags_fail_before_camera_import(self):
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            main(['--model','unused.task','--rehearsal','--no-overlay'])

    def test_sparse_capture_cannot_pass_a_thirty_second_interval(self):
        check=RehearsalCheck(strum_hand='Right',source='webcam',transmission='dry-run')
        check.confirm(ord('c'),0,HAND);check.confirm(ord('z'),0,ZONE_HAND)
        check.observe(.1,.11,[dict(value=.2)],HAND,False,control_hand='Right')
        check.observe(30.,30.01,[dict(value=.8)],HAND,False,control_hand='Right')
        self.assertTrue(check.done)
        self.assertFalse(check.report()['passed'])
        self.assertFalse(check.report()['checks']['no_frame_gap_over500ms'])

    def test_configured_hand_cannot_disappear_for_most_of_the_check(self):
        check=RehearsalCheck(strum_hand='Right',source='webcam',transmission='udp',seconds=1)
        check.confirm(ord('c'),0,HAND);check.confirm(ord('z'),0,ZONE_HAND)
        for i in range(1,11):
            check.observe(i*.1,i*.1+.01,[dict(value=i/10)],HAND if i==1 else [],False,control_hand='Right')
        self.assertTrue(check.done)
        self.assertFalse(check.report()['passed'])
        self.assertFalse(check.report()['checks']['configured_hand_visible_80_percent'])

    def test_other_hands_movement_cannot_qualify_the_configured_strum_hand(self):
        check=RehearsalCheck(strum_hand='Right',source='webcam',transmission='udp',seconds=1)
        check.confirm(ord('c'),0,HAND);check.confirm(ord('z'),0,ZONE_HAND)
        for i in range(1,11):
            check.observe(i*.1,i*.1+.01,[dict(value=i/10)],HAND,False,control_hand='Left')
        self.assertTrue(check.done)
        self.assertFalse(check.report()['passed'])
        self.assertEqual(check.report()['control_hand_events']['Left'],10)
        self.assertEqual(check.report()['configured_hand_events'],0)
