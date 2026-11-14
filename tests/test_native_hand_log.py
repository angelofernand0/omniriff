"""Actual native main loop with a deterministic detector fixture, no camera claim."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import numpy as np
from vision.__main__ import main
from vision.eyes import report_for_window


class NativeHandLogTests(unittest.TestCase):
    def test_main_logs_every_hand_before_control_selection(self):
        clock=[0.]
        class Capture:
            def __init__(self,*args):self.count=0;self.released=False
            def isOpened(self):return True
            def get(self,key):return 30
            def read(self):
                self.count+=1;clock[0]+=1/30
                return (self.count<=90,np.zeros((480,640,3),np.uint8))
            def release(self):self.released=True
        class Detector:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def detect_for_video(self,*args):
                n=round(clock[0]*30)
                hands=[[NS(x=.3,y=.4) for _ in range(21)],[NS(x=.7,y=.6) for _ in range(21)]] if n not in range(20,25) else []
                labels=[[NS(category_name='Left',score=.95)],[NS(category_name='Right',score=.97)]] if hands else []
                return NS(hand_landmarks=hands,handedness=labels)
        cv=NS(VideoCapture=Capture,CAP_PROP_FPS=1,COLOR_BGR2RGB=1,cvtColor=lambda frame,mode:frame,destroyAllWindows=lambda:None)
        mp=NS(Image=lambda image_format,data:data,ImageFormat=NS(SRGB=1),tasks=NS(BaseOptions=lambda **kw:kw,vision=NS(
            HandLandmarkerOptions=lambda **kw:kw,RunningMode=NS(VIDEO=1),HandLandmarker=NS(create_from_options=lambda options:Detector()))))
        with tempfile.TemporaryDirectory() as folder,patch.dict('sys.modules',{'cv2':cv,'mediapipe':mp}),patch('vision.__main__.time.monotonic',side_effect=lambda:clock[0]),patch('vision.__main__.time.time',side_effect=lambda:1000+clock[0]),patch('vision.__main__.time.sleep'),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            path=Path(folder)/'both.jsonl'
            main(['--model','synthetic.task','--video','synthetic.avi','--no-overlay','--no-hand-view','--dry-run','--hand-log',str(path),'--strum-hand','Left','--calibration',str(Path(folder)/'absent.json')])
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(rows),90)
            self.assertEqual(sum(len(row['hands'])==2 for row in rows),85)
            self.assertEqual(sum(not row['hands'] for row in rows),5)
            self.assertEqual(rows[0]['strum_hand'],'Left')
            self.assertEqual(rows[0]['timestamp_ms'],1000033)
            report=report_for_window(path,1000000,1003000,'native-fixture')
            self.assertTrue(report['available'])
            self.assertEqual(report['selected_hand'],'Left')
            self.assertEqual(report['sample_count'],85)
            self.assertGreater(report['tracking_gaps'],0)
