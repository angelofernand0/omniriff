"""Coach safety and contract checks run without network or a model key."""
from __future__ import annotations

import json
import os
from importlib.util import find_spec
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from coach.budget import BudgetGuard, estimate_upper_bound_usd
from coach.feed import CoachFeed, VALIDATOR, allowed_origin
from coach.memory import last_time_cue, prepare_fixture_workspace, remember_comparison
from coach.rig import RigClient, RigStateReader, control_message
from coach.runner import CoachRunner, _pending_actions
from coach.tools import CoachTools


class CoachFeedTests(unittest.TestCase):
    def test_full_frames_validate_and_origins_are_loopback_only(self):
        feed = CoachFeed("session-test", port=0)
        self.assertTrue(VALIDATOR.is_valid(feed.frame))
        self.assertTrue(VALIDATOR.is_valid(feed.publish(state="thinking", target="loop")))
        for origin in (None, "http://127.0.0.1:8081", "http://localhost:8081", "http://[::1]:8081"):
            self.assertTrue(allowed_origin(origin), origin)
        for origin in ("null", "https://example.com", "http://evil.localhost", "http://127.0.0.1.evil.com",
                       "http://evil@localhost:8081", "file:///tmp/index.html", "http://localhost:bad"):
            self.assertFalse(allowed_origin(origin), origin)

    def test_decisions_require_schema_and_matching_id(self):
        feed = CoachFeed("session-test")
        valid = {"version": 1, "type": "coach.approve", "timestamp_ms": 123, "approval_id": "right"}
        self.assertFalse(feed.accept_decision({"type": "coach.approve"}))
        self.assertTrue(feed.accept_decision({**valid, "approval_id": "wrong"}))
        self.assertTrue(feed.accept_decision(valid))
        self.assertEqual(feed.poll_decision("right"), "approve")
        self.assertIsNone(feed.poll_decision("right"))

    def test_player_words_are_validated_and_queued_for_the_brain(self):
        feed = CoachFeed("session-test")
        said = {"version": 1, "type": "coach.say", "timestamp_ms": 1, "text": "I've been struggling with this change", "via": "voice"}
        self.assertFalse(feed.accept_say({**said, "text": ""}))
        self.assertFalse(feed.accept_say({**said, "text": "x" * 241}))
        self.assertFalse(feed.accept_say({**said, "type": "coach.approve"}))
        self.assertTrue(feed.accept_say(said))
        self.assertFalse(feed.accept_decision(said))          # never mistaken for an approval
        self.assertEqual(feed.poll_said(), "I've been struggling with this change")
        self.assertIsNone(feed.poll_said())


class CoachRigTests(unittest.TestCase):
    def test_controls_are_schema_valid_and_fixture_mode_never_sends(self):
        self.assertEqual(control_message("filter", 0.4, 1, 123)["source"], "coach")
        self.assertEqual(control_message("bypass", None, 2, 124)["type"], "action")
        with self.assertRaises(ValueError):
            control_message("loop", 0.5, 3, 125)
        with self.assertRaises(ValueError):
            control_message("filter", float("nan"), 4, 126)
        rig = RigClient(fixture_mode=True, port=1)
        self.assertEqual(rig.send("reverb", 0.2)["seq"], 0)
        self.assertEqual(rig.send("loop")["seq"], 1)
        self.assertEqual(len(rig.sent), 2)

    def test_recording_counter_only_counts_transitions(self):
        reader = RigStateReader()
        reader.observe({"loop": {"state": "idle"}})
        reader.observe({"loop": {"state": "recording"}})
        reader.observe({"loop": {"state": "recording"}})
        self.assertEqual(reader.recording_counter(), 1)
        reader.observe({"loop": {"state": "playing"}})
        reader.observe({"loop": {"state": "recording"}})
        self.assertEqual(reader.recording_counter(), 2)

    def test_stale_state_is_unavailable(self):
        reader = RigStateReader()
        with patch("coach.rig.time.monotonic", return_value=100.0):
            reader.observe({"loop": {"state": "idle"}, "bypass": False})
        with patch("coach.rig.time.monotonic", return_value=103.0):
            self.assertEqual(reader.snapshot(), {"available": False})
        reader.observe({"loop": {"state": "idle"}, "bypass": False})
        reader.mark_disconnected()
        self.assertEqual(reader.snapshot(), {"available": False})


class CoachMemoryTests(unittest.TestCase):
    def test_fixture_profile_is_separate_and_preserves_its_own_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            live = root / "live"
            fixture = root / "fixture"
            (live / "skills" / "dry-check").mkdir(parents=True)
            (live / "skills" / "dry-check" / "SKILL.md").write_text("Synthetic test skill.\n")
            (live / "memories").mkdir()
            (live / "AGENTS.md").write_text("Test instructions.\n")
            (live / "memories" / "player.example.md").write_text("No prior sessions.\n")
            (live / "memories" / "player.md").write_text("Real-player history stays private.\n")
            prepare_fixture_workspace(live, fixture)
            self.assertNotIn("Real-player", (fixture / "memories" / "player.md").read_text())
            comparison = {"worst_gap_ms": [400, 120], "hesitations": [3, 0]}
            remember_comparison(fixture, comparison, synthetic=True)
            self.assertIn("synthetic replay", last_time_cue(fixture))
            prepare_fixture_workspace(live, fixture)
            self.assertIn("Verified synthetic take", (fixture / "memories" / "player.md").read_text())
            self.assertEqual((live / "memories" / "player.md").read_text(),
                             "Real-player history stays private.\n")
            self.assertIsNone(last_time_cue(live))


class CoachToolTests(unittest.TestCase):
    def test_rig_state_tool_reports_real_activity(self):
        with tempfile.TemporaryDirectory() as folder:
            feed = CoachFeed("session-test")
            state = RigStateReader()
            tools = CoachTools(Path(folder), feed, RigClient(fixture_mode=True), state)
            self.assertEqual(tools.get_rig_state(), {"available": False})
            self.assertEqual(feed.frame["activity"][-1],
                             {"who": "coach", "what": "get_rig_state", "status": "failed"})
            state.observe({"loop": {"state": "idle"}, "bypass": False})
            self.assertFalse(tools.get_rig_state()["bypass"])
            self.assertEqual(feed.frame["activity"][-1]["status"], "done")

    def test_report_tools_compare_and_card_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            feed = CoachFeed("session-test")
            tools = CoachTools(workspace, feed, RigClient(fixture_mode=True), RigStateReader())
            for take_id, gap, hes in (("before", 900, 3), ("after", 620, 0)):
                directory = workspace / "takes" / take_id
                directory.mkdir(parents=True)
                (directory / "take.json").write_text(json.dumps({
                    "take_id": take_id, "judgeable": True, "intervals_ms": [500, 500, gap],
                    "tempo_stability": 0.9, "findings": [{"type": "hesitation"}] * hes,
                }))
            self.assertEqual(tools.get_hand_report("before"), {"available": False, "take_id": "before"})
            self.assertEqual(tools.get_take_report("before")["take_id"], "before")
            result = tools.compare_takes("before", "after")
            self.assertEqual(result["hesitations"], [3, 0])
            self.assertEqual(result["worst_gap_ms"], [400, 120])
            self.assertTrue(result["improved"])
            self.assertTrue(VALIDATOR.is_valid(feed.frame))
            tools.current_take_id = "after"
            path = tools.write_drill_card("keep-the-hand-moving", "change near 2.7 s", 4,
                                         "worst gap under 700 ms", {"bypass": True})
            self.assertTrue((workspace / path.lstrip("/")).is_file())
            self.assertEqual(feed.frame["drill_card"]["skill"], "keep-the-hand-moving")
            self.assertEqual(feed.frame["session"]["metric"]["history"], [400.0, 120.0])
            self.assertEqual(feed.frame["session"]["metric"]["target"], 700.0)
            with patch("coach.voice.Voice.from_env") as make_voice:
                with patch.object(feed, "broadcast_audio") as broadcast:
                    self.assertEqual(tools.say("The gap is 620 ms. Keep the arm moving."),
                                     "The gap is 620 ms. Keep the arm moving.")
                    make_voice.assert_not_called()
                    broadcast.assert_not_called()
                    self.assertEqual(feed.frame["cue"], "The gap is 620 ms. Keep the arm moving.")
            with self.assertRaises(ValueError):
                tools.get_take_report("../private")

    def test_short_or_legacy_reports_never_publish_a_comparison(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            feed = CoachFeed("session-test")
            tools = CoachTools(workspace, feed, RigClient(fixture_mode=True), RigStateReader())
            for take_id, judgeable in (("before", True), ("short", False), ("legacy", None)):
                directory = workspace / "takes" / take_id
                directory.mkdir(parents=True)
                report = {"take_id": take_id, "intervals_ms": [], "findings": []}
                if judgeable is not None:
                    report["judgeable"] = judgeable
                (directory / "take.json").write_text(json.dumps(report))
            for after_id in ("short", "legacy"):
                with self.assertRaisesRegex(ValueError, "enough strums"):
                    tools.compare_takes("before", after_id)
            self.assertIsNone(feed.frame["before_after"])

    def test_toggle_tools_require_fresh_state_and_do_not_reverse_or_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            feed = CoachFeed("session-test")
            state = RigStateReader()
            rig = RigClient(fixture_mode=True)
            tools = CoachTools(Path(folder), feed, rig, state)
            self.assertIn("unavailable", tools.rig_control("bypass"))
            self.assertEqual(rig.sent, [])
            state.observe({"loop": {"state": "idle"}, "bypass": False})
            self.assertIn("Fixture logged", tools.rig_control("bypass"))
            self.assertIn("confirmation", tools.rig_control("bypass"))
            self.assertEqual(len(rig.sent), 1)
            state.observe({"loop": {"state": "recording"}, "bypass": True})
            self.assertIn("already active", tools.rig_control("bypass"))
            self.assertIn("already active", tools.rig_control("loop"))
            state.observe({"loop": {"state": "playing"}, "bypass": True})
            self.assertIn("not idle", tools.rig_control("loop"))
            state.observe({"loop": {"state": "idle"}, "bypass": True})
            self.assertIn("Fixture logged", tools.rig_control("loop"))
            self.assertIn("confirmation", tools.rig_control("loop"))
            self.assertEqual([event["control"] for event in rig.sent], ["bypass", "loop"])


class CoachRunnerTests(unittest.TestCase):
    def test_duplicate_toggle_requests_cannot_share_one_approval(self):
        result = {"__interrupt__": [SimpleNamespace(value={"action_requests": [
            {"name": "rig_control", "args": {"control": "bypass"}},
            {"name": "rig_control", "args": {"control": "bypass"}},
        ]})]}
        with self.assertRaisesRegex(ValueError, "duplicate toggle"):
            _pending_actions(result)

    def test_toggle_with_a_value_is_proposed_not_a_lost_take(self):
        """Live on Railway: the model asked for bypass with value=true and the whole take failed."""
        result = {"__interrupt__": [SimpleNamespace(value={"action_requests": [
            {"name": "rig_control", "args": {"control": "bypass", "value": 1}},
            {"name": "rig_control", "args": {"control": "reverb", "value": 0.2}},
        ]})]}
        self.assertEqual(_pending_actions(result), [{"control": "bypass"}, {"control": "reverb", "value": 0.2}])

    def test_unjudgeable_take_skips_agent_and_preserves_valid_baseline(self):
        from tools.ears.analyze import TakeReport

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            feed = CoachFeed("session-test")
            state = RigStateReader()
            service = CoachTools(root / "workspace", feed, RigClient(fixture_mode=True), state)
            runner = CoachRunner(None, service, feed, state, BudgetGuard(root / "usage.jsonl"),
                                 fixture_mode=True)
            reports = [
                TakeReport(take_id="before", judgeable=True, strum_count=4,
                           intervals_ms=[500, 500, 900], findings=[{"type": "hesitation"}]),
                TakeReport(take_id="short", judgeable=False, strum_count=0,
                           summary="Only 0 strums detected: too few to judge timing."),
                TakeReport(take_id="after", judgeable=True, strum_count=4,
                           intervals_ms=[500, 500, 620]),
            ]
            with patch("tools.ears.analyze.analyze_take", side_effect=reports), \
                 patch.object(runner, "_invoke", return_value={}) as invoke:
                for take_id in ("before", "short", "after"):
                    wav = root / f"{take_id}.wav"
                    sidecar = wav.with_suffix(".json")
                    sidecar.write_text(json.dumps({"take_id": take_id, "started_unix_ms": 0,
                                                   "ended_unix_ms": 1000}))
                    result = runner.process_take(wav, sidecar)
                    if take_id == "short":
                        self.assertEqual(result["skipped"], "unjudgeable")
                        self.assertEqual(runner.previous_take_id, "before")
                        self.assertIsNone(feed.frame["before_after"])
            self.assertEqual(invoke.call_count, 2)
            self.assertEqual(feed.frame["before_after"]["worst_gap_ms"], [400.0, 120.0])
            self.assertEqual(runner.previous_take_id, "after")
            self.assertNotIn("short", (root / "workspace" / "memories" / "player.md").read_text())

    @unittest.skipUnless(find_spec("langchain_core"), "coach/requirements.txt is optional in core CI")
    def test_synthetic_take_pipeline_with_fake_agent_and_no_engine(self):
        from langgraph.types import Command
        from coach.fixtures.generate import generate

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            takes = root / "fixtures"
            generate(takes)
            feed = CoachFeed("session-test")
            state = RigStateReader()
            state.observe({"loop": {"state": "idle"}, "bypass": False})
            rig = RigClient(fixture_mode=True, port=1)
            service = CoachTools(root / "workspace", feed, rig, state)

            class FakeAgent:
                def invoke(self, payload, config):
                    if isinstance(payload, Command):
                        assert payload.resume == {"decisions": [{"type": "approve"}]}
                        service.rig_control("bypass")
                        return {"messages": []}
                    take_id = service.current_take_id
                    assert service.get_take_report(take_id)["take_id"] == take_id
                    assert len(service.get_hand_report(take_id)["stalls"]) == (3 if take_id == "coach-before" else 0)
                    service.write_drill_card("keep-the-hand-moving", "change near 2.7 s", 4,
                                             "smaller measured gap", {"bypass": True})
                    return {"__interrupt__": [SimpleNamespace(value={"action_requests": [
                        {"name": "rig_control", "args": {"control": "bypass"}}
                    ]})], "todos": [{"content": "Set up a drill", "status": "in_progress"}]}

            runner = CoachRunner(FakeAgent(), service, feed, state, BudgetGuard(root / "usage.jsonl"),
                                 fixture_mode=True, auto_approve_fixtures=True)
            runner.process_take(takes / "coach-before.wav")
            runner.process_take(takes / "coach-after.wav")
            self.assertEqual(len(rig.sent), 1)
            self.assertEqual(feed.frame["before_after"]["worst_gap_ms"], [400.0, 120.0])
            self.assertTrue(feed.frame["before_after"]["improved"])
            self.assertEqual(feed.frame["state"], "pleased")
            self.assertEqual(feed.frame["mood"], "proud")
            self.assertTrue(VALIDATOR.is_valid(feed.frame))
            self.assertEqual(len((root / "usage.jsonl").read_text().splitlines()), 2)
            runner.open_session()
            self.assertTrue(feed.frame["cue"].startswith("Last time in synthetic replay"))

    @unittest.skipUnless(find_spec("langchain_core"), "coach/requirements.txt is optional in core CI")
    def test_fake_agent_interrupt_resumes_only_after_fixture_approval(self):
        from langgraph.types import Command

        class FakeAgent:
            def __init__(self):
                self.calls = []

            def invoke(self, payload, config):
                self.calls.append(payload)
                if len(self.calls) == 1:
                    return {"__interrupt__": [SimpleNamespace(value={"action_requests": [
                        {"name": "rig_control", "args": {"control": "bypass"}}
                    ]})], "todos": [{"content": "Set up dry drill", "status": "in_progress"}]}
                self_test.assertIsInstance(payload, Command)
                self_test.assertEqual(payload.resume, {"decisions": [{"type": "approve"}]})
                return {"messages": []}

        self_test = self
        with tempfile.TemporaryDirectory() as folder:
            feed = CoachFeed("session-test")
            state = RigStateReader()
            service = CoachTools(Path(folder), feed, RigClient(fixture_mode=True), state)
            fake = FakeAgent()
            runner = CoachRunner(fake, service, feed, state, BudgetGuard(Path(folder) / "usage.jsonl"),
                                 fixture_mode=True, auto_approve_fixtures=True)
            runner._invoke("New take before", "before")
            self.assertEqual(len(fake.calls), 2)
            self.assertEqual(feed.frame["todos"][0]["status"], "in_progress")

    def test_pedal_hold_approves_before_new_recording_and_is_consumed(self):
        with tempfile.TemporaryDirectory() as folder:
            feed = CoachFeed("session-test")
            state = RigStateReader()
            state.observe({"loop": {"state": "playing"}, "pedal": {"practice_count": 0}})
            service = CoachTools(Path(folder), feed, RigClient(fixture_mode=True), state)
            runner = CoachRunner(None, service, feed, state, BudgetGuard(Path(folder) / "usage.jsonl"),
                                 fixture_mode=True, approval_timeout_s=1)
            runner._session_active = True

            def hold():
                time.sleep(0.05)
                state.observe({"loop": {"state": "playing"}, "pedal": {"practice_count": 1}})

            thread = threading.Thread(target=hold)
            thread.start()
            self.assertTrue(runner._await_approval([{"control": "bypass"}]))
            thread.join()
            self.assertEqual(state.recording_counter(), 0)
            self.assertEqual(runner._last_practice_count, 1)
            runner._poll_practice_action()
            self.assertTrue(runner._session_active)
            self.assertEqual(service.session.mode, "practice")
            self.assertIsNone(feed.frame["awaiting_approval"])
            self.assertTrue(VALIDATOR.is_valid(feed.frame))

    def test_loop_taps_do_not_approve_pending_rig_change(self):
        with tempfile.TemporaryDirectory() as folder:
            feed = CoachFeed("session-test")
            state = RigStateReader()
            state.observe({"loop": {"state": "playing"}, "pedal": {"practice_count": 0}})
            service = CoachTools(Path(folder), feed, RigClient(fixture_mode=True), state)
            runner = CoachRunner(None, service, feed, state, BudgetGuard(Path(folder) / "usage.jsonl"),
                                 fixture_mode=True, approval_timeout_s=0.35)

            def taps():
                time.sleep(0.05)
                state.observe({"loop": {"state": "idle"}, "pedal": {"practice_count": 0}})
                time.sleep(0.05)
                state.observe({"loop": {"state": "recording"}, "pedal": {"practice_count": 0}})

            thread = threading.Thread(target=taps)
            thread.start()
            self.assertFalse(runner._await_approval([{"control": "bypass"}]))
            thread.join()
            self.assertEqual(state.recording_counter(), 1)
            self.assertEqual(service.rig.sent, [])
            self.assertIsNone(feed.frame["awaiting_approval"])

    def test_budget_guard_uses_conservative_logged_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            guard = BudgetGuard(Path(folder) / "usage.jsonl")
            self.assertTrue(guard.allow_new_run())
            estimate = estimate_upper_bound_usd({"model": {"input_tokens": 1_000_000, "output_tokens": 0}})
            self.assertEqual(estimate, 2.0)   # conservative accounting rate, not a provider price
            guard.record("synthetic-test", {"model": {"input_tokens": 4_000_000, "output_tokens": 0}}, 1.0)   # $8 = the cap
            self.assertFalse(guard.allow_new_run())


@unittest.skipUnless(find_spec("deepagents"), "coach/requirements.txt is optional in core CI")
class CoachAgentTests(unittest.TestCase):
    def test_harness_has_planning_subagents_and_no_shell_tool(self):
        from coach.agent import build_agent
        from coach.smoke import tool_names

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GOOGLE_API_KEY": "offline-test-key"}):
            root = Path(folder)
            (root / "AGENTS.md").write_text("Offline test workspace.\n")
            feed = CoachFeed("session-test")
            service = CoachTools(root, feed, RigClient(fixture_mode=True), RigStateReader())
            agent = build_agent(service)
            names = tool_names(agent)
            self.assertTrue({"write_todos", "task", "rig_control", "read_file", "edit_file"} <= names)
            self.assertNotIn("execute", names)


if __name__ == "__main__":
    unittest.main()
