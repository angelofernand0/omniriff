"""Run the native main loop on labeled landmark fixtures, never a second pipeline."""
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


def run_trace(trace, guarded):
    clock=[0.]
    frames=[]
    class Capture:
        def __init__(self,*args):self.index=0
        def isOpened(self):return True
        def get(self,key):return 30
        def read(self):
            if self.index>=len(trace):return False,None
            self.index+=1;clock[0]+=1/30
            return True,np.zeros((480,640,3),np.uint8)
        def release(self):pass
    class Detector:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def detect_for_video(self,*args):
            y,pinch,confidence=trace[round(clock[0]*30)-1]
            if y is None:return NS(hand_landmarks=[],handedness=[])
            hand=[NS(x=.5,y=.5) for _ in range(21)]
            hand[0]=NS(x=.5,y=y);hand[5]=NS(x=.4,y=.5);hand[17]=NS(x=.6,y=.5)
            hand[8]=NS(x=.5+.2*pinch,y=.5)
            other=[NS(x=.85,y=.5) for _ in range(21)]
            return NS(hand_landmarks=[hand,other],handedness=[
                [NS(category_name='Right',score=confidence)],[NS(category_name='Left',score=.95)]])
    class View:
        error=None
        def __init__(self,*args):pass
        def start(self):return self
        def publish(self,frame):frames.append(frame)
        def close(self):pass
    cv=NS(VideoCapture=Capture,CAP_PROP_FPS=1,COLOR_BGR2RGB=1,cvtColor=lambda frame,mode:frame,destroyAllWindows=lambda:None)
    mp=NS(Image=lambda image_format,data:data,ImageFormat=NS(SRGB=1),tasks=NS(BaseOptions=lambda **kw:kw,vision=NS(
        HandLandmarkerOptions=lambda **kw:kw,RunningMode=NS(VIDEO=1),HandLandmarker=NS(create_from_options=lambda options:Detector()))))
    stdout,stderr=io.StringIO(),io.StringIO()
    with tempfile.TemporaryDirectory() as folder,patch.dict('sys.modules',{'cv2':cv,'mediapipe':mp}),patch('vision.__main__.HandView',View),patch('vision.__main__.time.monotonic',side_effect=lambda:clock[0]),patch('vision.__main__.time.time',side_effect=lambda:1000+clock[0]),patch('vision.__main__.time.sleep'),contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
        root=Path(folder)
        args=['--model','fixture.task','--video','fixture.avi','--no-overlay','--dry-run','--relative',
              '--calibration',str(root/'absent.json'),'--hand-log',str(root/'hands.jsonl'),
              '--metrics-json',str(root/'metrics.json')]
        if guarded:args.append('--strum-guard')
        main(args)
        rows=[json.loads(line) for line in (root/'hands.jsonl').read_text().splitlines()]
        metrics=json.loads((root/'metrics.json').read_text())
    events=[json.loads(line) for line in stdout.getvalue().splitlines()]
    summary=json.loads(stderr.getvalue().splitlines()[-1])
    return NS(events=events,frames=frames,rows=rows,metrics=metrics,summary=summary)


class NativeStrumGuardTests(unittest.TestCase):
    def test_post_arm_strum_is_blocked_only_when_opted_in(self):
        trace=[(.4,.6,.95),(.56,.1,.95)]+[(.65+(.07 if i%2 else -.07),.1,.95) for i in range(60)]
        baseline=run_trace(trace,False)
        protected=run_trace(trace,True)
        self.assertGreater(len(baseline.events),10)
        self.assertEqual(protected.events,[])
        self.assertEqual(protected.summary['suppressed_frames'],61)
        self.assertTrue(all(frame['present'] for frame in protected.frames))
        self.assertTrue(all(len(frame['landmarks'])==21 for frame in protected.frames))
        self.assertTrue(all(len(row['hands'])==2 for row in protected.rows))
        self.assertEqual(protected.metrics['hand_present_frames'],len(trace))

    def test_air_drag_still_emits_and_loss_needs_fresh_arm(self):
        drag=[(.4,.6,.95),(.4,.1,.95)]+[(.4+i*.004,.1,.95) for i in range(20)]
        initial=run_trace(drag,True)
        self.assertGreater(len(initial.events),3)
        trace=drag+[(None,None,0),(.4,.1,.95),(.35,.1,.95),(.4,.1,.2),(.4,.1,.95)]
        result=run_trace(trace,True)
        self.assertEqual(result.events,initial.events)
        self.assertFalse(result.frames[-1]['engaged'])

    def test_zone_exit_stays_disarmed_then_picks_up_last_relative_value(self):
        drag=[(.4,.6,.95),(.4,.1,.95)]+[(.48,.1,.95)]*12
        initial=run_trace(drag,True)
        retained=initial.events[-1]['value']
        trace=drag+[(.65,.1,.95)]*3+[(.4,.1,.95)]*15+[(.4,.6,.95),(.4,.1,.95)]
        result=run_trace(trace,True)
        self.assertEqual(result.events,initial.events)
        self.assertAlmostEqual(result.frames[-1]['value'],retained)
        self.assertTrue(result.frames[-1]['engaged'])

    def test_lower_zone_boundary_is_inclusive(self):
        boundary=run_trace([(.55,.6,.95),(.55,.1,.95)],True)
        above=run_trace([(.549,.6,.95),(.549,.1,.95)],True)
        self.assertEqual(boundary.events,[])
        self.assertEqual(boundary.summary['suppressed_frames'],2)
        self.assertEqual(len(above.events),1)
        self.assertEqual(above.summary['suppressed_frames'],0)

    def test_rapid_reversals_above_zone_suppress_motion(self):
        trace=[(.3,.6,.95),(.3,.1,.95)]+[(.25 if i%2 else .45,.1,.95) for i in range(40)]
        baseline=run_trace(trace,False)
        protected=run_trace(trace,True)
        self.assertGreater(protected.summary['suppressed_frames'],20)
        self.assertLess(len(protected.events),len(baseline.events))
        self.assertFalse(protected.frames[-1]['engaged'])
