"""Hosted coach server (coach/server.py) without a model, key or network."""
import asyncio
import base64
import json
import tempfile
import unittest
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace

try:
    import numpy as np
    from coach import server
except ImportError:  # minimal CI without numpy/jsonschema
    server = None


class FakeConnection:
    def respond(self, status, text):
        return (status, text)


def request(path, origin="http://127.0.0.1:5173"):
    return SimpleNamespace(path=path, headers={"Origin": origin} if origin else {})


class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send(self, payload):
        self.sent.append(json.loads(payload))


@unittest.skipIf(server is None, "coach server dependencies not installed")
class CoachServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.srv = server.CoachServer(passcode="team-pass", origins=set(server.DEFAULT_ORIGINS),
                                      data=self.data, max_sessions=1)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, path, origin="http://127.0.0.1:5173"):
        result = self.srv.process_request(FakeConnection(), request(path, origin))
        return result[0] if result else None

    def test_gate(self):
        good = "/coach?player=p-0123456789"      # the passcode is never in the URL
        self.assertIsNone(self.check(good))
        self.assertIsNone(self.check(good, origin="https://omniriff.vercel.app"))
        self.assertEqual(self.check(good, origin="https://evil.example"), HTTPStatus.FORBIDDEN)
        self.assertEqual(self.check("/coach?player=../x"), HTTPStatus.BAD_REQUEST)
        self.assertEqual(self.check("/healthz"), HTTPStatus.OK)
        self.assertEqual(self.check("/other"), HTTPStatus.NOT_FOUND)
        self.srv.sessions.add(object())
        self.assertEqual(self.check(good), HTTPStatus.SERVICE_UNAVAILABLE)

    def test_passcode_is_checked_in_the_first_message(self):
        self.assertTrue(self.srv.authorized("team-pass"))
        for wrong in ("nope", "", None, 5, "team-pass "):
            self.assertFalse(self.srv.authorized(wrong))

        class HelloSocket(FakeSocket):
            def __init__(self, first):
                super().__init__()
                self.first = first
                self.closed = None
                self.request = SimpleNamespace(path="/coach?player=p-0123456789")

            async def recv(self):
                return self.first

            async def close(self, code, reason):
                self.closed = (code, reason)

        async def run(first):
            sock = HelloSocket(first)
            await self.srv.handle(sock)
            return sock
        for first in (json.dumps({"type": "omniriff.hello", "key": "nope"}),
                      json.dumps({"type": "coach.say", "text": "hi"}), "not json"):
            sock = asyncio.run(run(first))
            self.assertEqual(sock.closed[0], 4401)
            self.assertEqual(sock.sent, [])          # nothing about the coach before the passcode
            self.assertEqual(self.srv.sessions, set())

    def test_take_upload_control_and_practice(self):
        async def run():
            sock = FakeSocket()
            session = server.Session(self.srv, sock, "p-0123456789")
            sr = 16000
            t = np.arange(sr * 2) / sr
            pcm = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2").tobytes()
            hands = [{"timestamp_ms": 1_800_000_000_000 + i * 33, "wrist": [0.5, 0.5], "confidence": 0.9}
                     for i in range(10)] + [{"timestamp_ms": 5, "wrist": [2, 2]}]
            result = session.take({"samplerate": sr, "started_unix_ms": 1_800_000_000_000,
                                   "pcm16_b64": base64.b64encode(pcm).decode(), "hands": hands})
            self.assertEqual(result, "ok")
            sidecar = json.loads(next(session.takes.glob("*.json")).read_text())
            self.assertEqual(sidecar["samplerate"], sr)
            self.assertAlmostEqual(sidecar["seconds"], 2.0, places=2)
            lines = session.hand_log.read_text().splitlines()
            self.assertEqual(len(lines), 10)  # the out-of-range sample is dropped
            self.assertEqual(json.loads(lines[0])["strum_hand"], "Right")
            self.assertEqual(session.take({"samplerate": 3, "started_unix_ms": 1, "pcm16_b64": ""}), "bad samplerate")
            self.assertEqual(session.take({"samplerate": sr, "started_unix_ms": 1,
                                           "pcm16_b64": base64.b64encode(b"\0\0" * 100).decode()}),
                             "take length out of range")
            session.rig.send("bypass")
            session.practice()
            await asyncio.sleep(0.05)
            self.assertIn({"type": "omniriff.control", "control": "bypass", "value": None}, sock.sent)
            self.assertEqual(session.state.snapshot()["pedal"]["practice_count"], 1)
            self.assertTrue((session.workspace / "skills").is_dir())
            session.close()
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
