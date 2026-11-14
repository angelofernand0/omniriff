"""Riff's voice (roadmap R4): ElevenLabs text-to-speech, cached, never blocking, never fatal.

Owned by SM's Claude. The coach brain (SM's Codex) calls it from the `say` tool; the scripted
coach session (tools/sim/coach.py) uses it too.

    voice = Voice.from_env()                 # None-safe: works without a key (returns no audio)
    msg = await voice.render("Keep it swinging.")   # a coach.audio message, or None
    feed.broadcast(msg)

- The key (ELEVENLABS_API_KEY) is read from the environment, then the repo-root .env, then
  ~/.config/omniriff/.env. It stays in this process: only MP3 bytes go to the dashboard.
- Every cue is cached on disk by (voice, model, text), so rehearsals don't spend the free plan's
  monthly characters and a repeated cue plays instantly even with no network.
- Any failure (no key, no network, quota, timeout) returns None; the dashboard then falls back
  to the browser's voice. Voice never breaks the coach.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = 'https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128'
RIFF_VOICE = 'rHWSYoq8UlV0YIBKMryp'  # SM's pick from the voice library, Starter plan (2026-11-14)
JESSICA = 'cgSgspJ2msm6clMCkdW9'     # free-plan default voice, kept as a fallback (OMNIRIFF_VOICE_ID)
# Expressive but steady: lower stability lets the delivery move like a person's; a little style
# adds warmth without hamming it up (BRAND_SPEC.md section 7, Riff's voice).
SETTINGS = {'stability': 0.4, 'similarity_boost': 0.8, 'style': 0.25, 'use_speaker_boost': True}
MODEL = 'eleven_flash_v2_5'         # ~0.27 s per cue, measured
CACHE = Path.home() / '.cache' / 'omniriff' / 'voice'
TIMEOUT_S = 4.0


def env_value(name: str) -> str | None:
    """os.environ, else the first .env (repo root, then ~/.config/omniriff) that defines it."""
    if os.environ.get(name):
        return os.environ[name]
    for path in (ROOT / '.env', Path.home() / '.config' / 'omniriff' / '.env'):
        try:
            for line in path.read_text().splitlines():
                key, sep, value = line.strip().partition('=')
                if sep and key.strip() == name and value.strip():
                    return value.strip().strip('"').strip("'")
        except OSError:
            continue
    return None


def _ssl_context():
    """certifi's CA bundle when installed (python.org builds on macOS ship without system CAs;
    deepagents/httpx pull certifi in), else the platform default."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _http_fetch(url: str, headers: dict, body: bytes, timeout: float) -> bytes:
    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        return resp.read()


class Voice:
    def __init__(self, api_key: str | None, voice_id: str = RIFF_VOICE, model: str = MODEL,
                 cache_dir: Path = CACHE, fetch=_http_fetch, timeout: float = TIMEOUT_S):
        self.api_key, self.voice_id, self.model = api_key, voice_id, model
        self.cache_dir, self.fetch, self.timeout = Path(cache_dir), fetch, timeout
        self.last_error: str | None = None

    @classmethod
    def from_env(cls, **kw) -> 'Voice':
        return cls(env_value('ELEVENLABS_API_KEY'), voice_id=env_value('OMNIRIFF_VOICE_ID') or RIFF_VOICE, **kw)

    def _cache_path(self, text: str) -> Path:
        h = hashlib.sha256(f'{self.voice_id}|{self.model}|{json.dumps(SETTINGS, sort_keys=True)}|{text}'.encode()).hexdigest()[:32]
        return self.cache_dir / f'{h}.mp3'

    def synthesize(self, text: str) -> bytes | None:
        """MP3 bytes for text, from cache or ElevenLabs; None on any failure. Blocking."""
        text = text.strip()
        if not text:
            return None
        path = self._cache_path(text)
        try:
            return path.read_bytes()
        except OSError:
            pass
        if not self.api_key:
            self.last_error = 'no ELEVENLABS_API_KEY'
            return None
        try:
            mp3 = self.fetch(API.format(voice=self.voice_id),
                             {'xi-api-key': self.api_key, 'content-type': 'application/json', 'accept': 'audio/mpeg'},
                             json.dumps({'text': text, 'model_id': self.model, 'voice_settings': SETTINGS}).encode(), self.timeout)
        except Exception as e:  # network, 4xx quota/permission, timeout: all fall back to the browser voice
            self.last_error = type(e).__name__
            return None
        if not mp3 or mp3[:1] == b'{':  # JSON error body instead of audio
            self.last_error = 'not audio'
            return None
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix('.tmp')
            tmp.write_bytes(mp3)
            tmp.replace(path)
        except OSError:
            pass  # an uncached cue still plays
        return mp3

    def message(self, text: str, mp3: bytes) -> dict:
        """A coach.audio message (protocol/coach.schema.json)."""
        return {'version': 1, 'type': 'coach.audio', 'timestamp_ms': int(time.time() * 1000),
                'text': text.strip(), 'mime': 'audio/mpeg', 'audio_b64': base64.b64encode(mp3).decode()}

    @staticmethod
    def seconds(msg: dict | None, text: str = '') -> float:
        """How long a line takes to say: from the coach.audio MP3 (128 kbps), else estimated from
        the words. Pace the session with it: hold each line this long plus ~0.9 s before the next."""
        if msg and msg.get('audio_b64'):
            return len(msg['audio_b64']) * 3 / 4 * 8 / 128_000
        return max(1.2, len((text or (msg or {}).get('text', '')).split()) / 2.6)

    async def render(self, text: str) -> dict | None:
        """coach.audio for text, synthesized off the event loop; None if there's no audio."""
        mp3 = await asyncio.to_thread(self.synthesize, text)
        return self.message(text, mp3) if mp3 else None


if __name__ == '__main__':  # python -m coach.voice "Some cue"  → writes riff.mp3, reports cache/errors
    import sys
    v = Voice.from_env()
    t0 = time.time()
    out = v.synthesize(' '.join(sys.argv[1:]) or 'Keep it swinging through the change.')
    if out:
        Path('riff.mp3').write_bytes(out)
        print(f'riff.mp3 {len(out)} bytes in {time.time() - t0:.2f}s (voice {v.voice_id})')
    else:
        print(f'no audio: {v.last_error}')
