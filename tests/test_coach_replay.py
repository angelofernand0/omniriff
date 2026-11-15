"""Coach replay is private, validated, read-only, and needs no model/network call."""
from __future__ import annotations

import builtins
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coach import __main__ as coach_cli
from coach.feed import CoachFeed, VALIDATOR
from coach.replay import CoachReplayRecorder, ReplayError, play_replay, replay_events


AUDIO = {"version": 1, "type": "coach.audio", "timestamp_ms": 123,
         "text": "Keep the arm moving.", "mime": "audio/mpeg", "audio_b64": "AAAA"}


class CoachReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private.jsonl"

    def record_sample(self):
        recorder = CoachReplayRecorder(self.path)
        live = CoachFeed("original-session", tap=recorder.record)
        recorder.record(live.frame)
        live.publish(state="listening", cue="Keep the arm moving.", take_id="take-1")
        live.publish_activity("ears", "analyze_take", "done")
        self.assertTrue(live.broadcast_audio(AUDIO))
        recorder.close()

    def test_feed_tap_records_frames_activity_and_audio_without_input(self):
        self.record_sample()
        events = list(replay_events(self.path))
        self.assertEqual([e["message"]["type"] for e in events],
                         ["coach.frame", "coach.frame", "coach.frame", "coach.audio"])
        self.assertEqual(events[-1]["message"], AUDIO)
        self.assertEqual(events[2]["message"]["activity"][-1]["who"], "ears")
        self.assertEqual(events[1]["message"]["take_id"], "take-1")
        self.assertTrue(all(a["at_ms"] <= b["at_ms"] for a, b in zip(events, events[1:])))
        self.assertEqual(json.loads(self.path.read_text().splitlines()[0])["input_provenance"], "unverified")
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            CoachReplayRecorder(self.path)

    def test_replay_preserves_order_and_cue_but_never_reopens_approval_or_say(self):
        self.record_sample()
        replay = CoachFeed("replay-test", scripted=True, read_only=True)
        observed = []
        original_publish = replay.publish
        original_audio = replay.broadcast_audio

        def publish(**changes):
            frame = original_publish(**changes)
            observed.append(("frame", frame.copy()))
            return frame

        def audio(message):
            observed.append(("audio", message.copy()))
            return original_audio(message)

        with patch.object(replay, "publish", side_effect=publish), patch.object(replay, "broadcast_audio", side_effect=audio):
            self.assertEqual(play_replay(self.path, replay), 4)
        self.assertEqual([kind for kind, _ in observed], ["frame", "frame", "frame", "audio"])
        self.assertTrue(all(frame["scripted"] for kind, frame in observed if kind == "frame"))
        self.assertTrue(all(frame["session_id"] == "replay-test" for kind, frame in observed if kind == "frame"))
        self.assertEqual(replay.frame["cue"], "Keep the arm moving.")
        self.assertEqual(observed[-1][1]["text"], replay.frame["cue"])
        self.assertFalse(replay.accept_decision({"version": 1, "type": "coach.approve",
                                                 "timestamp_ms": 1, "approval_id": "approval"}))
        say = {"version": 1, "type": "coach.say", "timestamp_ms": 1,
               "text": "do this", "via": "typed"}
        self.assertTrue(VALIDATOR.is_valid(say))
        self.assertFalse(replay.accept_say(say))
        self.assertTrue(replay.decisions.empty())
        self.assertTrue(replay.said.empty())

    def test_invalid_or_partial_capture_is_rejected_before_publishing(self):
        self.record_sample()
        lines = self.path.read_text().splitlines()
        bad = json.loads(lines[-1])
        bad["at_ms"] = -1
        lines[-1] = json.dumps(bad)
        self.path.write_text("\n".join(lines) + "\n")
        replay = CoachFeed("replay-test", scripted=True, read_only=True)
        with self.assertRaisesRegex(ReplayError, "invalid coach replay event"):
            play_replay(self.path, replay)
        self.assertEqual(replay.frame["state"], "idle")

    def test_negative_first_offset_and_boolean_header_timestamp_are_rejected(self):
        self.record_sample()
        original = self.path.read_text().splitlines()
        first = json.loads(original[1])
        first["at_ms"] = -1
        self.path.write_text("\n".join([original[0], json.dumps(first), *original[2:]]) + "\n")
        with self.assertRaisesRegex(ReplayError, "event 1"):
            list(replay_events(self.path))
        header = json.loads(original[0])
        header["captured_at_ms"] = True
        self.path.write_text("\n".join([json.dumps(header), *original[1:]]) + "\n")
        with self.assertRaisesRegex(ReplayError, "header"):
            list(replay_events(self.path))
        header["captured_at_ms"] = json.loads(original[0])["captured_at_ms"]
        header["version"] = True
        self.path.write_text("\n".join([json.dumps(header), *original[1:]]) + "\n")
        with self.assertRaisesRegex(ReplayError, "header"):
            list(replay_events(self.path))

    def test_source_changes_during_playback_do_not_change_validated_snapshot(self):
        self.record_sample()
        replay = CoachFeed("replay-test", scripted=True, read_only=True)
        original_publish = replay.publish
        published = []

        def publish(**changes):
            if not published:
                self.path.write_text("corrupted source after snapshot\n")
            frame = original_publish(**changes)
            published.append(frame)
            return frame

        with patch.object(replay, "publish", side_effect=publish):
            self.assertEqual(play_replay(self.path, replay), 4)
        self.assertEqual(len(published), 3)
        self.assertEqual(replay.frame["cue"], "Keep the arm moving.")

    def test_only_outbound_messages_and_read_only_feed_are_accepted(self):
        recorder = CoachReplayRecorder(self.path, input_provenance="synthetic_fixture")
        with self.assertRaises(ValueError):
            recorder.record({"type": "coach.say"})
        recorder.close()
        with self.assertRaises(ReplayError):
            list(replay_events(self.path))
        with self.assertRaises(ValueError):
            play_replay(self.path, CoachFeed("live-session"))

    def test_capture_write_failure_does_not_break_coach_frame(self):
        def failed_tap(_message):
            raise OSError("disk full")

        feed = CoachFeed("live-session", tap=failed_tap)
        with patch("coach.feed.logging.exception") as report:
            feed.publish(state="thinking")
            feed.publish(state="idle")
        self.assertEqual(feed.frame["state"], "idle")
        report.assert_called_once()

    def test_replay_cli_never_imports_key_model_or_rig(self):
        real_import = builtins.__import__
        optional = {"agent", "budget", "memory", "rig", "runner", "smoke", "tools"}

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if (level == 1 and name in optional) or name in {f"coach.{part}" for part in optional}:
                self.fail(f"replay imported optional coach module {name}")
            return real_import(name, globals, locals, fromlist, level)

        with (patch.object(coach_cli, "CoachFeed") as feed_class,
              patch.object(coach_cli, "play_replay", side_effect=KeyboardInterrupt),
              patch("builtins.__import__", side_effect=guarded_import)):
            self.assertEqual(coach_cli.main(["--replay", str(self.path), "--feed-port", "0"]), 0)
        feed_class.assert_called_once()
        self.assertTrue(feed_class.call_args.kwargs["scripted"])
        self.assertTrue(feed_class.call_args.kwargs["read_only"])


if __name__ == "__main__":
    unittest.main()
