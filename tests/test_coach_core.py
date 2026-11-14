"""Coach safety and contract checks run without network or a model key."""
from __future__ import annotations

import json
import os
from importlib.util import find_spec
import tempfile
import threading
import time
import unittest
from unittest.mock import AsyncMock, patch
from pathlib import Path
from types import SimpleNamespace

from coach.budget import BudgetGuard, estimate_upper_bound_usd
from coach.feed import CoachFeed, VALIDATOR, allowed_origin
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


class CoachToolTests(unittest.TestCase):
    def test_report_tools_compare_and_card_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            feed = CoachFeed("session-test")
            tools = CoachTools(workspace, feed, RigClient(fixture_mode=True), RigStateReader())
            for take_id, gap, hes in (("before", 900, 3), ("after", 620, 0)):
                directory = workspace / "takes" / take_id
                directory.mkdir(parents=True)
                (directory / "take.json").write_text(json.dumps({
                    "take_id": take_id, "intervals_ms": [500, 500, gap],
                    "tempo_stability": 0.9, "findings": [{"type": "hesitation"}] * hes,
                }))
            self.assertEqual(tools.get_hand_report("before"), {"available": False, "take_id": "before"})
            self.assertEqual(tools.get_take_report("before")["take_id"], "before")
            result = tools.compare_takes("before", "after")
            self.assertEqual(result["hesitations"], [3, 0])
            self.assertEqual(result["worst_gap_ms"], [900, 620])
            self.assertTrue(result["improved"])
            self.assertTrue(VALIDATOR.is_valid(feed.frame))
            tools.current_take_id = "after"
            path = tools.write_drill_card("keep-the-hand-moving", "change near 2.7 s", 4,
                                         "worst gap under 700 ms", {"bypass": True})
            self.assertTrue((workspace / path.lstrip("/")).is_file())
            self.assertEqual(feed.frame["drill_card"]["skill"], "keep-the-hand-moving")
            with patch("coach.voice.Voice.from_env") as make_voice:
                audio = {"version": 1, "type": "coach.audio", "timestamp_ms": 123,
                         "text": "The gap is 620 ms. Keep the arm moving.",
                         "mime": "audio/mpeg", "audio_b64": "AAAA"}
                make_voice.return_value.render = AsyncMock(return_value=audio)
                with patch.object(feed, "broadcast_audio") as broadcast:
                    self.assertEqual(tools.say("The gap is 620 ms. Keep the arm moving."),
                                     "The gap is 620 ms. Keep the arm moving.")
                    broadcast.assert_called_once_with(audio)
            with self.assertRaises(ValueError):
                tools.get_take_report("../private")


class CoachRunnerTests(unittest.TestCase):
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
            self.assertEqual(len(rig.sent), 2)
            self.assertEqual(feed.frame["before_after"]["worst_gap_ms"], [900.0, 620.0])
            self.assertTrue(feed.frame["before_after"]["improved"])
            self.assertTrue(VALIDATOR.is_valid(feed.frame))
            self.assertEqual(len((root / "usage.jsonl").read_text().splitlines()), 2)

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

    def test_pedal_recording_transition_approves_pending_actions(self):
        with tempfile.TemporaryDirectory() as folder:
            feed = CoachFeed("session-test")
            state = RigStateReader()
            state.observe({"loop": {"state": "idle"}})
            service = CoachTools(Path(folder), feed, RigClient(fixture_mode=True), state)
            runner = CoachRunner(None, service, feed, state, BudgetGuard(Path(folder) / "usage.jsonl"),
                                 fixture_mode=True, approval_timeout_s=1)

            def pedal():
                time.sleep(0.05)
                state.observe({"loop": {"state": "recording"}})

            thread = threading.Thread(target=pedal)
            thread.start()
            self.assertTrue(runner._await_approval([{"control": "bypass"}]))
            thread.join()
            self.assertIsNone(feed.frame["awaiting_approval"])
            self.assertTrue(VALIDATOR.is_valid(feed.frame))

    def test_budget_guard_uses_conservative_logged_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            guard = BudgetGuard(Path(folder) / "usage.jsonl")
            self.assertTrue(guard.allow_new_run())
            estimate = estimate_upper_bound_usd({"model": {"input_tokens": 1_000_000, "output_tokens": 0}})
            self.assertEqual(estimate, 15.0)
            guard.record("synthetic-test", {"model": {"input_tokens": 500_000, "output_tokens": 0}}, 1.0)
            self.assertFalse(guard.allow_new_run())


@unittest.skipUnless(find_spec("deepagents"), "coach/requirements.txt is optional in core CI")
class CoachAgentTests(unittest.TestCase):
    def test_harness_has_planning_subagents_and_no_shell_tool(self):
        from coach.agent import build_agent
        from coach.smoke import tool_names

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "offline-test-key"}):
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
