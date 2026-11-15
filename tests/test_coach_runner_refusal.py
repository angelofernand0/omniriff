"""B21: Offline regression tests for CoachRunner budget refusal and clean termination.

Covers preflight refusal, gate refusal mid-invoke, gate refusal mid-resume,
and clean termination with audio untouched and zero further model calls.
Synthetic usage accounting only; no live models, API keys, or paid calls.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from coach.budget import BudgetGuard
from coach.feed import CoachFeed, VALIDATOR
from coach.model_gate import ModelCallGate
from coach.rig import RigClient, RigStateReader
from coach.runner import BudgetExhausted, CoachRunner
from coach.tools import CoachTools
from tools.ears.analyze import TakeReport


def tokens(inputs: int = 0, outputs: int = 0) -> dict:
    return {"synthetic-model": {"input_tokens": inputs, "output_tokens": outputs}}


class CoachRunnerRefusalTests(unittest.TestCase):
    """B21: Budget refusal tests for CoachRunner."""

    def setUp(self):
        # Synthetic round rates keep the "budget exhausted" fixtures meaningful; real rates: test_coach_budget.
        for name, value in (("INPUT_USD_PER_M", 15.0), ("OUTPUT_USD_PER_M", 75.0), ("RUN_RESERVE_USD", 2.0)):
            patcher = patch(f"coach.budget.{name}", value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # Keep optional fakes local to the test. Installing them at discovery
        # time shadows real, not-yet-imported packages in the full coach suite.
        modules = {}
        try:
            from langchain_core.callbacks import UsageMetadataCallbackHandler
        except ImportError:
            callbacks = ModuleType("langchain_core.callbacks")

            class UsageMetadataCallbackHandler:
                def __init__(self):
                    self.usage_metadata = {}
                    self._lock = threading.Lock()

            callbacks.UsageMetadataCallbackHandler = UsageMetadataCallbackHandler
            modules["langchain_core.callbacks"] = callbacks
            if "langchain_core" not in sys.modules:
                modules["langchain_core"] = ModuleType("langchain_core")
        try:
            from langgraph.types import Command
        except ImportError:
            types = ModuleType("langgraph.types")

            class Command:
                def __init__(self, resume=None):
                    self.resume = resume

            types.Command = Command
            modules["langgraph.types"] = types
            if "langgraph" not in sys.modules:
                modules["langgraph"] = ModuleType("langgraph")
        if modules:
            imports = patch.dict(sys.modules, modules)
            imports.start()
            self.addCleanup(imports.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.usage_path = self.root / "usage.jsonl"
        self.feed = CoachFeed("session-test")
        self.state = RigStateReader()
        self.state.observe({"loop": {"state": "idle"}, "bypass": False})
        self.rig = RigClient(fixture_mode=True, port=1)
        self.service = CoachTools(self.root / "workspace", self.feed, self.rig, self.state)

    def _create_synthetic_take(self, take_dir: Path, take_id: str = "take-001") -> tuple[Path, Path]:
        take_dir.mkdir(parents=True, exist_ok=True)
        wav = take_dir / f"{take_id}.wav"
        wav.write_bytes(
            b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        )
        sidecar = take_dir / f"{take_id}.json"
        sidecar.write_text(
            json.dumps({"take_id": take_id, "wav": wav.name, "started_unix_ms": 1000, "ended_unix_ms": 3000})
        )
        return wav, sidecar

    def test_preflight_refusal_stops_invoke_protects_audio_and_emits_asleep_cue(self):
        """When budget.allow_new_run() is False before an invoke, coach refuses preflight."""
        # Limit $1.00, reserve $0.50. Recording 100k input tokens = $1.50 spent.
        guard = BudgetGuard(self.usage_path, limit_usd=1.0, reserve_usd=0.5)
        guard.record("prior-take", tokens(100_000), 0.1)
        self.assertFalse(guard.allow_new_run())

        class MockAgent:
            def __init__(self):
                self.calls = []

            def invoke(self, payload, config):
                self.calls.append(payload)
                return {}

        agent = MockAgent()
        runner = CoachRunner(agent, self.service, self.feed, self.state, guard, fixture_mode=True)

        with self.assertRaises(BudgetExhausted):
            runner._invoke("New take take-001", "take-001")

        # Zero model calls attempted
        self.assertEqual(len(agent.calls), 0)
        # Audio / rig untouched: no commands dispatched to audio engine
        self.assertEqual(len(self.rig.sent), 0)
        # Asleep state with exact preflight cue
        self.assertEqual(self.feed.frame["state"], "asleep")
        self.assertEqual(self.feed.frame["mood"], "sleepy")
        self.assertEqual(self.feed.frame["cue"], "Coach is out of credit.")
        self.assertTrue(VALIDATOR.is_valid(self.feed.frame))

    def test_preflight_refusal_terminates_run_directory_cleanly(self):
        """run_directory catches preflight BudgetExhausted and terminates without unhandled crash."""
        guard = BudgetGuard(self.usage_path, limit_usd=1.0, reserve_usd=0.5)
        guard.record("prior-take", tokens(100_000), 0.1)
        self.assertFalse(guard.allow_new_run())

        class MockAgent:
            def __init__(self):
                self.calls = []

            def invoke(self, payload, config):
                self.calls.append(payload)
                return {}

        agent = MockAgent()
        runner = CoachRunner(agent, self.service, self.feed, self.state, guard, fixture_mode=True)
        take_dir = self.root / "takes"
        wav, sidecar = self._create_synthetic_take(take_dir, "take-001")

        report = TakeReport(take_id="take-001", judgeable=True, strum_count=4, intervals_ms=[250, 250, 250])
        with patch("tools.ears.analyze.analyze_take", return_value=report):
            # run_directory must return cleanly without raising BudgetExhausted
            runner.run_directory(take_dir, once=True)

        self.assertEqual(len(agent.calls), 0)
        self.assertEqual(len(self.rig.sent), 0)
        self.assertEqual(self.feed.frame["state"], "asleep")
        self.assertEqual(self.feed.frame["cue"], "Coach is out of credit.")
        self.assertTrue(VALIDATOR.is_valid(self.feed.frame))

    def test_gate_refusal_mid_invoke_stops_specialists_protects_audio_and_emits_cue(self):
        """When the shared model gate refuses mid-invoke, runner terminates and cues player."""
        guard = BudgetGuard(self.usage_path, limit_usd=2.0, reserve_usd=0.5)
        self.assertTrue(guard.allow_new_run())

        gate = ModelCallGate(guard)
        self.service.model_gate = gate

        class MockAgentMidInvoke:
            def __init__(self):
                self.calls = []

            def invoke(self, payload, config):
                self.calls.append(payload)
                # Specialist call trips the model gate budget
                with patch.object(guard, "before_model_call", return_value=False):
                    try:
                        gate.call(lambda: None)
                    except BudgetExhausted:
                        pass
                return {"messages": []}

        agent = MockAgentMidInvoke()
        runner = CoachRunner(agent, self.service, self.feed, self.state, guard, fixture_mode=True)

        with self.assertRaises(BudgetExhausted):
            runner._invoke("New take take-002", "take-002")

        # Exactly 1 model call occurred; specialist refused; no further model calls
        self.assertEqual(len(agent.calls), 1)
        # Audio / rig untouched
        self.assertEqual(len(self.rig.sent), 0)
        # Asleep state with mid-invoke out-of-credit cue
        self.assertEqual(self.feed.frame["state"], "asleep")
        self.assertEqual(self.feed.frame["mood"], "sleepy")
        self.assertEqual(self.feed.frame["cue"], "Coach is out of credit; keep playing without me.")
        self.assertTrue(VALIDATOR.is_valid(self.feed.frame))
        # Gate callback unbound cleanly in finally block
        self.assertIsNone(gate._callback)

    def test_gate_refusal_mid_invoke_terminates_run_directory_cleanly(self):
        """run_directory cleanly exits when mid-invoke refusal raises BudgetExhausted."""
        guard = BudgetGuard(self.usage_path, limit_usd=2.0, reserve_usd=0.5)
        gate = ModelCallGate(guard)
        self.service.model_gate = gate

        class MockAgentMidInvoke:
            def __init__(self):
                self.calls = []

            def invoke(self, payload, config):
                self.calls.append(payload)
                with patch.object(guard, "before_model_call", return_value=False):
                    try:
                        gate.call(lambda: None)
                    except BudgetExhausted:
                        pass
                return {"messages": []}

        agent = MockAgentMidInvoke()
        runner = CoachRunner(agent, self.service, self.feed, self.state, guard, fixture_mode=True)
        take_dir = self.root / "takes"
        wav, sidecar = self._create_synthetic_take(take_dir, "take-002")

        report = TakeReport(take_id="take-002", judgeable=True, strum_count=4, intervals_ms=[250, 250, 250])
        with patch("tools.ears.analyze.analyze_take", return_value=report):
            runner.run_directory(take_dir, once=True)

        self.assertEqual(len(agent.calls), 1)
        self.assertEqual(len(self.rig.sent), 0)
        self.assertEqual(self.feed.frame["state"], "asleep")
        self.assertEqual(self.feed.frame["cue"], "Coach is out of credit; keep playing without me.")
        self.assertTrue(VALIDATOR.is_valid(self.feed.frame))

    def test_gate_refusal_mid_resume_blocks_rig_action_and_emits_asleep_cue(self):
        """When approval succeeds but resumed model call trips budget gate, action is aborted."""
        guard = BudgetGuard(self.usage_path, limit_usd=2.0, reserve_usd=0.5)
        self.assertTrue(guard.allow_new_run())

        gate = ModelCallGate(guard)
        self.service.model_gate = gate

        class MockAgentMidResume:
            def __init__(self):
                self.calls = []

            def invoke(self, payload, config):
                self.calls.append(payload)
                if len(self.calls) == 1:
                    # Turn 1: Propose rig action requiring HITL pedal approval
                    return {
                        "__interrupt__": [
                            SimpleNamespace(
                                value={"action_requests": [{"name": "rig_control", "args": {"control": "bypass"}}]}
                            )
                        ],
                        "todos": [{"content": "Setup bypass drill", "status": "in_progress"}],
                    }
                # Turn 2 (resumed after pedal approval): Gate trips on second model step
                with patch.object(guard, "before_model_call", return_value=False):
                    try:
                        gate.call(lambda: None)
                    except BudgetExhausted:
                        pass
                return {"messages": []}

        agent = MockAgentMidResume()
        runner = CoachRunner(
            agent,
            self.service,
            self.feed,
            self.state,
            guard,
            fixture_mode=True,
            auto_approve_fixtures=True,
        )

        with self.assertRaises(BudgetExhausted):
            runner._invoke("New take take-003", "take-003")

        # Initial invoke + 1 resumed invoke = exactly 2 calls; no loop progression
        self.assertEqual(len(agent.calls), 2)
        # Even though pedal approved the interrupt, the resumed model call was refused
        # before dispatching rig modifications -> audio engine untouched!
        self.assertEqual(len(self.rig.sent), 0)
        # Asleep state with mid-resume out-of-credit cue
        self.assertEqual(self.feed.frame["state"], "asleep")
        self.assertEqual(self.feed.frame["mood"], "sleepy")
        self.assertEqual(self.feed.frame["cue"], "Coach is out of credit; keep playing without me.")
        self.assertTrue(VALIDATOR.is_valid(self.feed.frame))
        self.assertIsNone(gate._callback)

    def test_gate_refusal_mid_resume_terminates_run_directory_cleanly(self):
        """run_directory catches mid-resume BudgetExhausted and terminates without unhandled crash."""
        guard = BudgetGuard(self.usage_path, limit_usd=2.0, reserve_usd=0.5)
        gate = ModelCallGate(guard)
        self.service.model_gate = gate

        class MockAgentMidResume:
            def __init__(self):
                self.calls = []

            def invoke(self, payload, config):
                self.calls.append(payload)
                if len(self.calls) == 1:
                    return {
                        "__interrupt__": [
                            SimpleNamespace(
                                value={"action_requests": [{"name": "rig_control", "args": {"control": "bypass"}}]}
                            )
                        ],
                        "todos": [{"content": "Setup bypass drill", "status": "in_progress"}],
                    }
                with patch.object(guard, "before_model_call", return_value=False):
                    try:
                        gate.call(lambda: None)
                    except BudgetExhausted:
                        pass
                return {"messages": []}

        agent = MockAgentMidResume()
        runner = CoachRunner(
            agent,
            self.service,
            self.feed,
            self.state,
            guard,
            fixture_mode=True,
            auto_approve_fixtures=True,
        )
        take_dir = self.root / "takes"
        wav, sidecar = self._create_synthetic_take(take_dir, "take-003")

        report = TakeReport(take_id="take-003", judgeable=True, strum_count=4, intervals_ms=[250, 250, 250])
        with patch("tools.ears.analyze.analyze_take", return_value=report):
            runner.run_directory(take_dir, once=True)

        self.assertEqual(len(agent.calls), 2)
        self.assertEqual(len(self.rig.sent), 0)
        self.assertEqual(self.feed.frame["state"], "asleep")
        self.assertEqual(self.feed.frame["cue"], "Coach is out of credit; keep playing without me.")
        self.assertTrue(VALIDATOR.is_valid(self.feed.frame))

    def test_unexpected_directory_exception_when_budget_exhausted_emits_asleep_cue(self):
        """When an unhandled exception hits run_directory with exhausted budget, it safely sleeps."""
        guard = BudgetGuard(self.usage_path, limit_usd=1.0, reserve_usd=0.5)
        guard.record("prior-take", tokens(100_000), 0.1)
        self.assertFalse(guard.allow_new_run())

        runner = CoachRunner(None, self.service, self.feed, self.state, guard, fixture_mode=True)
        take_dir = self.root / "takes"
        wav, sidecar = self._create_synthetic_take(take_dir, "take-error")

        with patch.object(runner, "process_take", side_effect=RuntimeError("unexpected sidecar read error")):
            runner.run_directory(take_dir, once=True)

        self.assertEqual(len(self.rig.sent), 0)
        self.assertEqual(self.feed.frame["state"], "asleep")
        self.assertEqual(self.feed.frame["cue"], "Coach is out of credit.")
        self.assertTrue(VALIDATOR.is_valid(self.feed.frame))


if __name__ == "__main__":
    unittest.main()
