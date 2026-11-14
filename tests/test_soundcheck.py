import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest

import numpy as np
from audio import Engine, EngineConfig
from engine.runtime import Runtime
from vision.hand_view import HandView
from vision.soundcheck.session import Session
from vision.soundcheck.__main__ import Feed, local_ws, run, ROOT
from vision.soundcheck.page import page


class SessionTests(unittest.TestCase):
    def drive(self,s,t,**kwargs):
        values=dict(value=.5,hand_present=True,engaged=True,confidence=.9,fresh=True)
        values.update(kwargs)
        return s.update(t,**values)

    def test_target_hold_release_requires_observed_hand(self):
        s=Session(targets=[.5])
        self.drive(s,0)
        self.drive(s,1.1)
        self.assertEqual(s.phase,'release')
        self.drive(s,1.2,hand_present=False,engaged=False)
        self.drive(s,2,hand_present=False,engaged=False)
        self.assertFalse(s.done)
        self.assertEqual(s.tracking_breaks,1)
        self.drive(s,2.1)
        self.drive(s,3.2)
        self.drive(s,3.3,engaged=False)
        self.drive(s,3.9,engaged=False)
        self.assertTrue(s.done)
        self.assertTrue(s.results[0]['passed'])

    def test_stale_manual_only_and_wrong_mode_cannot_pass(self):
        for flags in ({'fresh':False},{'engaged':False},{'control':None},{'confidence':.2}):
            s=Session(targets=[.5],timeout=3)
            self.drive(s,0,**flags)
            self.drive(s,1.1,**flags)
            self.drive(s,2,**flags)
            self.drive(s,3.1,**flags)
            self.assertTrue(s.done)
            self.assertFalse(s.results[0]['passed'])

    def test_release_drift_requires_reacquisition(self):
        s=Session(targets=[.5])
        self.drive(s,0)
        self.drive(s,1.1)
        self.drive(s,1.2,engaged=False,value=.8)
        self.assertEqual(s.phase,'reach')
        self.assertFalse(s.done)
        with self.assertRaises(ValueError): self.drive(s,.1)

    def test_feed_freshness_requires_connection_receive_and_source_clock(self):
        f=Feed({'type':'object'})
        f.value={'timestamp_ms':100000}
        f.connected=True
        f.received=10
        self.assertTrue(f.fresh(10.1,100.1))
        self.assertFalse(f.fresh(10.6,100.1))
        self.assertFalse(f.fresh(10.1,102))
        f.connected=False
        self.assertFalse(f.fresh(10.1,100.1))

    def test_duplicate_or_reordered_messages_do_not_refresh_feed(self):
        f=Feed({'type':'object'})
        self.assertTrue(f.accept({'timestamp_ms':1000},1))
        self.assertFalse(f.accept({'timestamp_ms':1000},1.4))
        self.assertFalse(f.accept({'timestamp_ms':999},1.5))
        self.assertEqual(f.received,1)
        self.assertTrue(f.accept({'timestamp_ms':1001},1.6))

    def test_local_only_and_report_cannot_inject_script(self):
        self.assertEqual(local_ws('ws://127.0.0.1:47801'),'ws://127.0.0.1:47801')
        for bad in ('wss://example.com:443','ws://user:pass@localhost:1234','ws://localhost','ws://localhost:99999'):
            with self.assertRaises(argparse.ArgumentTypeError): local_ws(bad)
        html=page({'source_label':'</script><script>evil()</script>'})
        self.assertNotIn('</script><script>evil()',html)


class SoundcheckIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancellation_saves_incomplete_report_without_touching_old_output(self):
        with tempfile.TemporaryDirectory() as folder:
            args=argparse.Namespace(targets=[.5],timeout=5,output=Path(folder)/'check',http_port=0,
                source_label='UNAVAILABLE FEED TEST',engine_ws='ws://127.0.0.1:1',hand_ws='ws://127.0.0.1:1')
            task=asyncio.create_task(run(args))
            await asyncio.sleep(.15)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            report=json.loads((args.output/'report.json').read_text())
            self.assertFalse(report['complete'])
            self.assertEqual(report['results'],[])
            before=(args.output/'report.json').read_bytes()
            with self.assertRaises(FileExistsError):
                await run(args)
            self.assertEqual((args.output/'report.json').read_bytes(),before)

    async def test_real_engine_and_hand_transport_complete_and_preserve_rig(self):
        audio=Engine(EngineConfig(samplerate=16000))
        audio.set_filter(.5)
        audio.process(np.zeros(128,np.float32),np.zeros((128,2),np.float32))
        runtime=Runtime(audio,udp_port=0,ws_port=0)
        hand=HandView(0).start()
        await runtime.start()
        async def publish():
            started=time.monotonic()
            while True:
                elapsed=time.monotonic()-started
                hand.publish(dict(version=1,type='hand',timestamp_ms=int(time.time()*1000),present=True,
                                  engaged=elapsed<2,confidence=.95,control='filter',value=.5,landmarks=[[.5,.5]]*21))
                await asyncio.sleep(.04)
        producer=None
        try:
            for _ in range(100):
                if hand.ready.is_set() and runtime.server is not None: break
                await asyncio.sleep(.01)
            with tempfile.TemporaryDirectory() as folder:
                args=argparse.Namespace(targets=[.5],timeout=5,output=Path(folder)/'check',http_port=0,
                    source_label='SYNTHETIC TEST FEED',engine_ws=f'ws://127.0.0.1:{runtime.ws_port}',hand_ws=f'ws://127.0.0.1:{hand.port}')
                producer=asyncio.create_task(publish())
                report=await asyncio.wait_for(run(args),7)
                self.assertTrue(report['complete'])
                self.assertTrue(report['results'][0]['passed'])
                self.assertEqual(audio.snapshot()['filter']['target'],.5)
                self.assertEqual(runtime.router.counts['accepted'],0) # Observer sends no commands.
                saved=json.loads((args.output/'report.json').read_text())
                self.assertEqual(saved['source_label'],'SYNTHETIC TEST FEED')
                self.assertIn('OBSERVED CONTROL SOUNDCHECK',(args.output/'index.html').read_text())
        finally:
            if producer:
                producer.cancel()
                await asyncio.gather(producer,return_exceptions=True)
            hand.close()
            await runtime.close()
