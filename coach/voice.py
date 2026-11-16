"""Compatibility shim for browser-local Riff speech.

Server TTS is disabled: no provider credentials, network requests, disk cache,
or prerecorded provider audio is used. The dashboard voices the cue text with
an available local browser voice, otherwise keeping the caption visible.
"""
from __future__ import annotations

import base64
import time


class Voice:
    def __init__(self, api_key=None, **legacy_options):
        # Accept old injected options so local callers can migrate without
        # accidentally retaining or using a credential/fetcher/cache location.
        self.api_key = None
        self.last_error = "Server TTS disabled; use browser-local speech or captions"

    @classmethod
    def from_env(cls, **legacy_options) -> "Voice":
        """Do not read environment files or existing paid-provider keys."""
        return cls(**legacy_options)

    def synthesize(self, text: str) -> None:
        """No server synthesis, even if an old key/cache/fetcher was supplied."""
        return None

    def message(self, text: str, mp3: bytes) -> dict:
        """Keep the existing recorded-audio envelope for offline/replay callers."""
        return {"version": 1, "type": "coach.audio", "timestamp_ms": int(time.time() * 1000),
                "text": text.strip(), "mime": "audio/mpeg",
                "audio_b64": base64.b64encode(mp3).decode()}

    @staticmethod
    def seconds(msg: dict | None, text: str = "") -> float:
        """Pace historical recordings or estimate caption/local-voice duration."""
        if msg and msg.get("audio_b64"):
            return len(msg["audio_b64"]) * 3 / 4 * 8 / 128_000
        return max(1.2, len((text or (msg or {}).get("text", "")).split()) / 2.6)

    async def render(self, text: str) -> None:
        return None


if __name__ == "__main__":
    print("Riff uses browser-local speech or captions. Server TTS is disabled.")
