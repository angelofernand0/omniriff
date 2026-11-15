"""Offline checks for the measured, two-drill practice-session projection."""
from __future__ import annotations

import unittest
import builtins
import json
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from coach.feed import CoachFeed
from coach.rig import RigClient, RigStateReader
from coach.session import PracticeSession
from coach.tools import CoachTools
from coach.budget import BudgetGuard
from coach.model_gate import ModelCallGate
from coach.runner import BudgetExhausted, CoachRunner
from tools.ears.analyze import TakeReport


def report(take_id: str, gap_ms: float, *, judgeable: bool = True) -> dict:
    return {"take_id": take_id, "judgeable": judgeable,
            "intervals_ms": [500, 500, 500, 500 + gap_ms]}   # steady beat + one strum gap_ms late


def card(title: str, skill: str) -> dict:
    return {"title": title, "skill": skill, "pass_rule": "longest gap under 150 ms"}


class PracticeSessionFlowTests(unittest.TestCase):
    def test_runner_hears_goal_and_completes_measured_two_drill_session(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            feed = CoachFeed("session-test")
            state = RigStateReader()
            service = CoachTools(root / "workspace", feed, RigClient(fixture_mode=True), state)
            prompts = []

            class Agent:
                def invoke(self, payload, config):
                    prompt = payload["messages"][0][1]
                    prompts.append(prompt)
                    service.get_take_report(service.current_take_id)
                    if "Session action: diagnose" in prompt:
                        service.write_drill_card("isolate-the-change", "The measured change", 3,
                                                 "longest gap under 300 ms", {})
                    elif "Session action: advance" in prompt:
                        service.write_drill_card("slow-then-speed-up", "The full pattern", 3,
                                                 "longest gap under 200 ms", {})
                    return {"messages": []}

            runner = CoachRunner(Agent(), service, feed, state, BudgetGuard(root / "usage.jsonl"),
                                 fixture_mode=True)
            feed.accept_say({"version": 1, "type": "coach.say", "timestamp_ms": 1,
                             "text": "Keep my rhythm steady at the change", "via": "typed"})
            runner._poll_player_input()
            self.assertEqual(service.session.goal, "Keep my rhythm steady at the change")
            self.assertIn("Keep my rhythm steady", (service.workspace / "journal" / "session-test" / "goal.md").read_text())

            reports = [
                TakeReport(take_id="base", judgeable=True, strum_count=4,
                           intervals_ms=[500, 500, 930],
                           findings=[{"type": "hesitation", "at_ms": 2000, "gap_ms": 930, "extra_ms": 430}]),
                TakeReport(take_id="try1", judgeable=True, strum_count=4,
                           intervals_ms=[500, 500, 850]),
                TakeReport(take_id="try2", judgeable=True, strum_count=4,
                           intervals_ms=[500, 500, 780]),
                TakeReport(take_id="full", judgeable=True, strum_count=4,
                           intervals_ms=[500, 500, 690]),
            ]
            with patch("tools.ears.analyze.analyze_take", side_effect=reports):
                for take_id in ("base", "try1", "try2", "full"):
                    wav = root / f"{take_id}.wav"
                    sidecar = wav.with_suffix(".json")
                    sidecar.write_text(json.dumps({"take_id": take_id, "started_unix_ms": 1000,
                                                   "ended_unix_ms": 4000}))
                    runner.process_take(wav, sidecar)
                    if take_id == "base":
                        self.assertEqual(feed.frame["mark"],
                                         {"start_s": 1.07, "end_s": 2.0, "label": "430 ms late"})
                    if take_id == "try1":
                        self.assertIsNone(feed.frame["mark"])
                        self.assertEqual(service.session.snapshot()["attempt"], {"n": 1, "of": 3})
            self.assertEqual(len(prompts), 4)
            self.assertIn("Player's goal", prompts[0])
            self.assertIn("Session action: retry", prompts[1])
            self.assertIn("Session action: advance", prompts[2])
            self.assertIn("Session action: wrap", prompts[3])
            self.assertEqual(service.session.mode, "play")
            self.assertEqual([item["status"] for item in feed.frame["session"]["plan"]], ["done", "done"])
            self.assertIn("430 to 190 ms", feed.frame["session"]["summary"])
            self.assertIsNotNone(feed.frame["session"]["next_time"])
            self.assertEqual(feed.frame["session"]["metric"]["history"], [430, 350, 280, 190])

    def test_practice_pedal_count_starts_and_pauses_without_claiming_pass(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            feed = CoachFeed("session-test")
            state = RigStateReader()
            service = CoachTools(root, feed, RigClient(fixture_mode=True), state)
            runner = CoachRunner(None, service, feed, state, BudgetGuard(root / "usage.jsonl"))
            state.observe({"loop": {"state": "idle"}, "pedal": {"practice_count": 1}})
            runner._poll_practice_action()
            self.assertTrue(runner._session_active)
            state.observe({"loop": {"state": "idle"}, "pedal": {"practice_count": 2}})
            runner._poll_practice_action()
            self.assertEqual(service.session.mode, "play")
            self.assertIsNone(service.session.summary)
            state.observe({"loop": {"state": "idle"}, "pedal": {"practice_count": 3}})
            runner._poll_practice_action()
            self.assertEqual(service.session.mode, "practice")
            self.assertIsNone(runner.previous_take_id)

    def test_model_gate_refusal_never_calls_handler_or_releases_unadmitted_call(self):
        class Guard:
            def __init__(self):
                self.allow = False
                self.seen = []
                self.releases = 0

            def before_model_call(self, usage):
                self.seen.append(usage)
                return self.allow

            def after_model_call(self, usage):
                self.seen.append(usage)
                self.releases += 1

        guard = Guard()
        gate = ModelCallGate(guard)
        class Callback:
            _lock = threading.Lock()
            usage_metadata = {"model": {"input_tokens": 3, "output_tokens": 2}}
        gate.bind(Callback())
        with self.assertRaises(BudgetExhausted):
            gate.call(lambda: self.fail("refused model call ran"))
        self.assertEqual(guard.seen, [Callback.usage_metadata])
        self.assertEqual(guard.releases, 0)
        guard.allow = True
        gate.bind(Callback())  # a fresh invocation clears the sticky refusal
        with self.assertRaisesRegex(RuntimeError, "model failure"):
            gate.call(lambda: (_ for _ in ()).throw(RuntimeError("model failure")))
        self.assertEqual(guard.releases, 1)
        self.assertEqual(guard.seen[-1], Callback.usage_metadata)

    def test_offline_runner_needs_no_optional_langchain_import(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            feed = CoachFeed("session-test")
            state = RigStateReader()
            service = CoachTools(root, feed, RigClient(fixture_mode=True), state)

            class FakeAgent:
                def invoke(self, payload, config):
                    self_test.assertEqual(config["callbacks"][0].usage_metadata, {})
                    return {"messages": []}

            self_test = self
            runner = CoachRunner(FakeAgent(), service, feed, state, BudgetGuard(root / "usage.jsonl"))
            real_import = builtins.__import__

            def without_optional(name, *args, **kwargs):
                if name == "langchain_core.callbacks":
                    raise ModuleNotFoundError("synthetic optional dependency absent")
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=without_optional):
                self.assertEqual(runner._invoke("offline", "synthetic-take"), {"messages": []})
            self.assertEqual(len((root / "usage.jsonl").read_text().splitlines()), 1)

    def test_agent_goal_tool_is_one_shot_and_schema_valid(self):
        with TemporaryDirectory() as folder:
            feed = CoachFeed("session-test")
            tools = CoachTools(Path(folder), feed, RigClient(fixture_mode=True), RigStateReader())
            with self.assertRaisesRegex(ValueError, "first TakeReport"):
                tools.set_practice_goal("Reduce the measured gap")
            tools.current_take_id = "first"
            with self.assertRaisesRegex(ValueError, "first TakeReport"):
                tools.set_practice_goal("Reduce the measured gap")
            take_dir = Path(folder) / "takes" / "first"
            take_dir.mkdir(parents=True)
            (take_dir / "take.json").write_text(json.dumps(report("first", 430)))
            tools.get_take_report("first")
            self.assertEqual(tools.set_practice_goal("Reduce the measured gap"), "Reduce the measured gap")
            self.assertEqual(feed.frame["session"]["goal"], "Reduce the measured gap")
            self.assertEqual([item["status"] for item in feed.frame["session"]["plan"]],
                             ["now", "next"])
            with self.assertRaisesRegex(ValueError, "already set"):
                tools.set_practice_goal("Guess a chord")

    def test_two_drills_three_attempt_limit_and_play_wrap(self):
        session = PracticeSession(last_time="Last time, the longest gap was 430 ms.")
        self.assertTrue(session.record_take(report("baseline", 430)))
        self.assertEqual(session.next_action("baseline")["action"], "diagnose")
        session.plan(goal="Reduce the measured gap at the change",
                     next_step="Isolate the change", drill_count=2,
                     attempt_count=3,
                     drill_titles=["Isolate the change", "Full pattern over your loop"])
        session.set_drill_card(card("Isolate the change", "isolate-the-change"))
        self.assertTrue(session.record_take(report("try-1", 300)))
        self.assertEqual(session.next_action("try-1")["action"], "retry")
        self.assertEqual(session.snapshot()["attempt"], {"n": 1, "of": 3})
        self.assertFalse(session.record_take(report("silence", 0, judgeable=False)))
        self.assertFalse(session.record_take(report("try-1", 300)))
        with self.assertRaisesRegex(ValueError, "three judged"):
            session.advance_drill(passed=False)
        self.assertTrue(session.record_take(report("try-2", 250)))
        self.assertTrue(session.record_take(report("try-3", 200)))
        self.assertEqual(session.assess_take("try-3")["passed"], False)
        self.assertEqual(session.next_action("try-3"),
                         {"action": "advance", "passed": False,
                          "assessment": session.assess_take("try-3")})
        self.assertEqual(session.snapshot()["metric"]["history"], [430, 300, 250, 200])
        session.advance_drill(passed=False, next_step="Full pattern over your loop")
        self.assertEqual([item["status"] for item in session.snapshot()["plan"]], ["skipped", "now"])
        session.set_drill_card(card("Full pattern over your loop", "slow-then-speed-up"))
        self.assertTrue(session.record_take(report("full-pattern", 120)))
        self.assertEqual(session.assess_take("full-pattern")["passed"], True)
        self.assertEqual(session.next_action("full-pattern")["action"], "wrap")
        session.finish("Longest measured gap: 430 to 120 ms. Next time, keep the hand moving.", passed=True)
        snapshot = session.snapshot()
        self.assertEqual(snapshot["mode"], "play")
        self.assertEqual(session.next_action("full-pattern")["action"], "ignore")
        self.assertEqual([item["status"] for item in snapshot["plan"]], ["skipped", "done"])
        self.assertIsNone(snapshot["drill"])
        self.assertIsNone(snapshot["attempt"])
        self.assertIsNone(snapshot["next"])
        self.assertEqual(snapshot["metric"]["history"], [430, 300, 250, 200, 120])
        feed = CoachFeed("session-test")
        self.assertEqual(feed.publish(session=snapshot)["session"], snapshot)

    def test_cannot_finish_early_or_invent_silent_progress(self):
        session = PracticeSession()
        session.plan(goal="Reduce a measured timing gap", drill_count=2, attempt_count=3,
                     drill_titles=["Isolate", "Full pattern"])
        session.set_drill_card(card("Isolate", "isolate-the-change"))
        self.assertFalse(session.record_take(report("silence", 0, judgeable=False)))
        with self.assertRaisesRegex(ValueError, "no judgeable"):
            session.assess_take("silence")
        self.assertEqual(session.snapshot()["metric"]["history"], [])
        with self.assertRaisesRegex(ValueError, "judged drill"):
            session.advance_drill(passed=False)
        with self.assertRaisesRegex(ValueError, "not ready"):
            session.finish("Done", passed=True)


if __name__ == "__main__":
    unittest.main()
