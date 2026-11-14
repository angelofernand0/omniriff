import asyncio
import json
import unittest
from websockets.asyncio.client import connect
from vision.hand_view import HandView


class HandViewTests(unittest.IsolatedAsyncioTestCase):
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
