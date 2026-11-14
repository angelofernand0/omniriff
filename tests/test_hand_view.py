import asyncio
import json
import unittest
from pathlib import Path
from jsonschema import Draft202012Validator
from websockets.asyncio.client import connect
from vision.hand_view import HandView


class HandViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_schema_over_real_transport(self):
        validator = Draft202012Validator(json.loads((Path(__file__).parents[1] / 'protocol/hand.schema.json').read_text()))
        feed = HandView(0).start()
        try:
            for _ in range(100):
                if feed.ready.is_set(): break
                await asyncio.sleep(.01)
            self.assertIsNone(feed.error)
            self.assertTrue(feed.ready.is_set())
            async with connect(f'ws://127.0.0.1:{feed.port}', origin='http://localhost:8080') as ws:
                for i, (present, engaged, control, value) in enumerate([
                    (False, False, 'filter', None), (True, False, 'filter', .3),
                    (True, True, 'reverb', .7), (True, True, None, .5),
                ]):
                    frame = dict(version=1, type='hand', timestamp_ms=i, present=present,
                                 engaged=engaged, control=control, value=value,
                                 confidence=.95 if present else 0,
                                 landmarks=[[.4, .6] for _ in range(21)] if present else [])
                    feed.publish(frame)
                    received = json.loads(await asyncio.wait_for(ws.recv(), 1))
                    validator.validate(received)
                    self.assertEqual(received, frame)
        finally:
            feed.close()

    async def test_latest_snapshot_disconnect_and_shutdown(self):
        feed = HandView(0).start()
        try:
            for _ in range(100):
                if feed.ready.is_set(): break
                await asyncio.sleep(.01)
            self.assertIsNone(feed.error)
            self.assertTrue(feed.ready.is_set())
            for i in range(1000):
                feed.publish(dict(version=1, type='hand', timestamp_ms=i, present=False,
                                  engaged=False, confidence=0, control='filter', value=None, landmarks=[]))
            self.assertLessEqual(feed.mailbox.qsize(), 1)
            await asyncio.sleep(.05)
            async with connect(f'ws://127.0.0.1:{feed.port}', origin='http://localhost:8080') as ws:
                frame = json.loads(await asyncio.wait_for(ws.recv(), 1))
                self.assertEqual(frame['timestamp_ms'], 999)
                self.assertEqual(frame['landmarks'], [])
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(ws.recv(), .15)  # Never refresh stale data by retransmitting.
            await asyncio.sleep(.3)
            async with connect(f'ws://127.0.0.1:{feed.port}') as ws:
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(ws.recv(), .15)  # New viewers must not get stale hands.
            feed.publish(frame)  # No client is required for publishing.
        finally:
            feed.close()
        self.assertFalse(feed.thread.is_alive())
