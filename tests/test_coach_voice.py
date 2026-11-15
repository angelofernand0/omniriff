"""Riff's voice (coach/voice.py): cache, fallbacks, coach.audio messages. No network: fetch is faked."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from coach.voice import Voice

ROOT = Path(__file__).resolve().parents[1]
COACH = Draft202012Validator(json.loads((ROOT / 'protocol/coach.schema.json').read_text()))
MP3 = b'ID3\x04fake-mp3-bytes'


class FakeFetch:
    def __init__(self, result=MP3, error=None):
        self.calls, self.result, self.error = [], result, error

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, json.loads(body)))
        if self.error:
            raise self.error
        return self.result


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def voice(self, key='k', **kw):
        return Voice(key, cache_dir=Path(self.tmp.name), **kw)

    def test_synthesizes_then_caches(self):
        fetch = FakeFetch()
        v = self.voice(fetch=fetch)
        self.assertEqual(v.synthesize('Keep it swinging.'), MP3)
        self.assertEqual(v.synthesize('Keep it swinging.'), MP3)      # second time from disk
        self.assertEqual(len(fetch.calls), 1)
        url, headers, body = fetch.calls[0]
        self.assertIn(v.voice_id, url)
        self.assertEqual(headers['xi-api-key'], 'k')
        self.assertEqual(body['text'], 'Keep it swinging.')
        self.assertEqual(body['model_id'], v.model)
        self.assertIn('stability', body['voice_settings'])

    def test_cache_works_without_key_or_network(self):
        self.voice(fetch=FakeFetch()).synthesize('Again?')
        offline = self.voice(key=None, fetch=FakeFetch(error=OSError('no network')))
        self.assertEqual(offline.synthesize('Again?'), MP3)

    def test_failures_return_none(self):
        self.assertIsNone(self.voice(key=None, fetch=FakeFetch()).synthesize('x'))
        self.assertIsNone(self.voice(fetch=FakeFetch(error=TimeoutError())).synthesize('x'))
        self.assertIsNone(self.voice(fetch=FakeFetch(result=b'{"detail":"quota"}')).synthesize('x'))
        self.assertIsNone(self.voice(fetch=FakeFetch()).synthesize('   '))

    def test_message_is_schema_valid_and_keyless(self):
        msg = asyncio.run(self.voice(fetch=FakeFetch()).render('Keep it swinging.'))
        self.assertEqual([e.message for e in COACH.iter_errors(msg)], [])
        self.assertNotIn('k', [v for v in msg.values() if isinstance(v, str) and len(v) < 3])
        self.assertNotIn('xi-api-key', json.dumps(msg))

    def test_scripted_session_speaks(self):
        from tools.sim.coach import run_scripted_coach
        v = self.voice(fetch=FakeFetch())

        async def go():
            from websockets.asyncio.client import connect
            q = asyncio.Queue()

            async def states():
                while True:
                    yield await q.get()
            port = asyncio.get_running_loop().create_future()
            task = asyncio.create_task(run_scripted_coach(0, udp_port=None, pace=0, states=states(),
                                                          ready=port.set_result, voice=v, start_round=True))
            audio = []
            async with connect(f'ws://127.0.0.1:{await port}') as ws:
                for s in ('idle', 'recording', 'playing'):
                    await q.put({'bypass': False, 'loop': {'state': s, 'seconds': 0, 'max_seconds': 30}})
                end = asyncio.get_running_loop().time() + 3
                while not audio and asyncio.get_running_loop().time() < end:
                    try:
                        m = json.loads(await asyncio.wait_for(ws.recv(), 0.5))
                    except asyncio.TimeoutError:
                        continue
                    if m['type'] == 'coach.audio':
                        audio.append(m)
            task.cancel()
            return audio

        audio = asyncio.run(go())
        self.assertTrue(audio)
        self.assertTrue(COACH.is_valid(audio[0]))


if __name__ == '__main__':
    unittest.main()
