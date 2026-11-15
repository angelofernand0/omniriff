"""Exercise the real browser worker/UDP path with explicitly synthetic landmarks."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import numpy as np
from audio import Engine,EngineConfig
from engine.runtime import Runtime
from tools.virtual_guitar.browser_vision import BrowserVision


class BrowserSliderPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_to_udp_engine_and_manual_repickup(self):
        class Detector:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def detect_for_video(self,image,stamp):
                y,pinch,confidence=image[0,0,:]/100
                if confidence==0:return NS(hand_landmarks=[],handedness=[])
                points=[NS(x=.5,y=.5) for _ in range(21)]
                # The wrist may be projected below the camera while the palm
                # is visible. The play-room controller must follow the palm.
                points[0]=NS(x=.5,y=float(y)+.25)
                points[9]=NS(x=.5,y=float(y))
                points[5]=NS(x=.4,y=.5);points[17]=NS(x=.6,y=.5)
                points[8]=NS(x=.5+.2*pinch,y=.5)
                points[16]=points[19]=points[20]=NS(x=.75,y=.5)
                return NS(hand_landmarks=[points],handedness=[[NS(score=float(confidence))]])
        def decode(data,mode):
            frame=np.zeros((480,640,3),np.uint8);frame[0,0,:]=data[:3];return frame
        cv=NS(imdecode=decode,cvtColor=lambda image,mode:image,IMREAD_COLOR=1,COLOR_BGR2RGB=1)
        mp=NS(Image=lambda image_format,data:data,ImageFormat=NS(SRGB=1),tasks=NS(
            BaseOptions=lambda **kw:kw,vision=NS(HandLandmarkerOptions=lambda **kw:kw,
                RunningMode=NS(VIDEO=1),HandLandmarker=NS(create_from_options=lambda options:Detector()))))
        audio=Engine(EngineConfig(samplerate=16000));audio.set_filter(.4)
        runtime=Runtime(audio,udp_port=0,ws_port=0)
        await runtime.start()
        output=np.zeros((128,2),np.float32)
        def pump():audio.process(np.zeros(128,np.float32),output)
        pump()
        camera=None
        try:
            for _ in range(100):
                if runtime.udp is not None:break
                await asyncio.sleep(.01)
            with tempfile.TemporaryDirectory() as folder,patch.dict('sys.modules',{'cv2':cv,'mediapipe':mp}):
                model=Path(folder)/'synthetic-model.task';model.write_text('mocked detector')
                camera=BrowserVision(model,udp_port=runtime.udp_port,hand_port=0,
                                     read_filter=lambda:audio.snapshot()['filter']['target'])
                camera.start()
                for _ in range(100):
                    if camera.status in ('waiting','error'):break
                    await asyncio.sleep(.01)
                self.assertIsNone(camera.error)
                async def frame(y,pinch,confidence=.95):
                    count=camera.frame_count
                    camera.submit(bytes([round(y*100),round(pinch*100),round(confidence*100)]))
                    for _ in range(100):
                        if camera.frame_count>count:break
                        await asyncio.sleep(.01)
                    self.assertGreater(camera.frame_count,count)
                    await asyncio.sleep(.065)
                    pump()
                await frame(.65,.6)
                await frame(.65,.1)
                self.assertEqual(camera.event_count,0)
                self.assertAlmostEqual(audio.snapshot()['filter']['target'],.4)
                await frame(.5,.1)
                self.assertGreater(audio.snapshot()['filter']['target'],.4)
                await frame(.5,.6)
                audio.set_filter(.2);pump()
                before=camera.event_count
                await frame(.5,.1)
                self.assertEqual(camera.event_count,before)
                self.assertAlmostEqual(audio.snapshot()['filter']['target'],.2)
                await frame(.35,.1)
                value=audio.snapshot()['filter']['target']
                self.assertGreater(value,.2)
                await frame(.25,.1,.2)
                await frame(.25,.1)
                self.assertAlmostEqual(audio.snapshot()['filter']['target'],value)
                await frame(.45,.6)
                await frame(.65,.6)
                await frame(.8,.6)  # wrist y=1.05, palm y=.8
                self.assertTrue(camera.snapshot()['hand_present'])
                self.assertTrue(camera.snapshot()['hand_confident'])
                self.assertTrue(camera.snapshot()['hand_armed'])
                await frame(.8,.1)
                self.assertTrue(camera.snapshot()['hand_engaged'])
                await frame(.6,.1)
                self.assertGreater(audio.snapshot()['filter']['target'],value)
                self.assertEqual(runtime.router.counts['duplicate'],0)
                metrics=camera.snapshot()['metrics']
                self.assertEqual(metrics['frames'],camera.frame_count)
                self.assertEqual(metrics['events'],camera.event_count)
                self.assertGreater(metrics['hand_present_frames'],0)
                camera.close()
                self.assertFalse(camera.thread.is_alive())
        finally:
            if camera:camera.close()
            await runtime.close()
