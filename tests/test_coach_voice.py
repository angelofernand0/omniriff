"""Old credentials, fetchers and caches cannot enable paid Riff synthesis."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jsonschema import Draft202012Validator
from coach.voice import Voice

ROOT = Path(__file__).resolve().parents[1]


class VoiceTests(unittest.TestCase):
    def test_supplied_legacy_provider_options_never_fetch_or_keep_a_key(self):
        fetch = Mock(side_effect=AssertionError("Paid synthesis must not run"))
        voice = Voice("old-test-key", fetch=fetch, voice_id="old-voice", model="old-model")
        self.assertIsNone(voice.synthesize("Keep it swinging."))
        self.assertIsNone(asyncio.run(voice.render("Keep it swinging.")))
        self.assertIsNone(voice.api_key)
        fetch.assert_not_called()

    def test_from_env_ignores_keys_and_does_not_read_dotenv_or_audio_cache(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "old-test-key"}), \
             patch.object(Path, "read_text", side_effect=AssertionError("No dotenv read")), \
             patch.object(Path, "read_bytes", side_effect=AssertionError("No cached voice read")):
            voice = Voice.from_env()
            self.assertIsNone(voice.api_key)
            self.assertIsNone(asyncio.run(voice.render("Again.")))

    def test_no_voice_files_are_written_even_when_a_cache_dir_is_supplied(self):
        with tempfile.TemporaryDirectory() as folder:
            voice = Voice("old-key", cache_dir=Path(folder))
            for text in ("A cue", "", "A cue"):
                self.assertIsNone(voice.synthesize(text))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_replay_envelope_remains_schema_valid(self):
        schema = json.loads((ROOT / "protocol/coach.schema.json").read_text())
        msg = Voice().message("Recorded cue", b"ID3-recorded-fixture")
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(msg)), [])
        self.assertNotIn("api_key", msg)

    def test_caption_and_recording_pacing_still_work(self):
        self.assertEqual(Voice.seconds(None, "one two"), 1.2)
        self.assertGreater(Voice.seconds(None, "one two three four five six"), 1.2)
        self.assertGreater(Voice.seconds(Voice().message("cue", b"x" * 16000)), 0)


if __name__ == "__main__":
    unittest.main()
