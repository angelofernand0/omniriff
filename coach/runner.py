"""Watch completed takes, analyze off-thread from audio, and run the coach."""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from .budget import BudgetGuard
from .feed import CoachFeed
from .rig import RigStateReader, control_message
from .tools import CoachTools, _safe_take_id


LOG = logging.getLogger(__name__)


class BudgetExhausted(RuntimeError):
    """No more paid model calls are allowed this session."""


def _todo_frame(result: dict) -> list[dict]:
    output = []
    for todo in result.get("todos", [])[:12]:
        if not isinstance(todo, dict):
            continue
        value = str(todo.get("content") or todo.get("text") or "")[:80]
        status = todo.get("status")
        if value and status in {"pending", "in_progress", "completed"}:
            output.append({"text": value, "status": status})
    return output


def _pending_actions(result: dict) -> list[dict]:
    """Extract and validate only rig_control requests from a Deep Agents interrupt."""
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return []
    requests = interrupts[0].value.get("action_requests", [])
    if not requests or len(requests) > 4:
        raise ValueError("invalid coach approval batch")
    actions = []
    for request in requests:
        if request.get("name") != "rig_control":
            raise ValueError("unexpected interrupted tool")
        args = request.get("args") or {}
        control = args.get("control")
        if control not in {"bypass", "filter", "reverb", "loop"}:
            raise ValueError("invalid rig action")
        action = {"control": control}
        if "value" in args and args["value"] is not None:
            action["value"] = args["value"]
        control_message(control, action.get("value"), 0, 0)
        actions.append(action)
    return actions


def _fixture_hand_report(log_path: Path, sidecar: dict) -> dict:
    """Use current Eyes logic on synthetic logs until R17's window API lands."""
    from dataclasses import asdict
    from vision.eyes import HandMovementAnalyzer

    if not log_path.is_file():
        return {"available": False}
    analyzer = HandMovementAnalyzer()
    start = int(sidecar["started_unix_ms"])
    end = int(sidecar["ended_unix_ms"])
    with log_path.open() as stream:
        for line in stream:
            sample = json.loads(line)
            stamp = sample.get("timestamp_ms")
            hands = sample.get("hands") or []
            if not isinstance(stamp, int) or not start <= stamp <= end or not hands:
                continue
            hand = next((h for h in hands if h.get("handedness") == "Right"), hands[0])
            wrist = hand.get("wrist")
            if isinstance(wrist, list) and len(wrist) == 2:
                analyzer.add_sample((stamp - start) / 1000, *wrist)
    report = asdict(analyzer.analyze())
    report.update(take_id=sidecar["take_id"], started_unix_ms=start,
                  source="vision.eyes/synthetic_fixture")
    for stall in report.get("stalls", []):
        stall["start_ms"] = round(stall["start_time_s"] * 1000)
        stall["end_ms"] = round(stall["end_time_s"] * 1000)
    return report


def hand_report(log_path: Path | None, sidecar: dict, *, fixture_mode: bool) -> dict:
    if log_path is None or not log_path.is_file():
        return {"available": False}
    if fixture_mode:
        return _fixture_hand_report(log_path, sidecar)
    try:
        from vision.eyes import report_for_window
    except ImportError:
        return {"available": False}
    try:
        report = report_for_window(
            log_path, sidecar["started_unix_ms"], sidecar["ended_unix_ms"],
            sidecar["take_id"], hand="strum",
        )
        from dataclasses import asdict, is_dataclass
        return asdict(report) if is_dataclass(report) else report
    except (ValueError, OSError, KeyError) as exc:
        LOG.warning("hand report unavailable: %s", exc)
        return {"available": False}


class CoachRunner:
    """Owns take processing; injected agent/feed/state permit no-network tests."""

    def __init__(
        self, agent, service: CoachTools, feed: CoachFeed, state: RigStateReader,
        budget: BudgetGuard, *, hand_log: Path | None = None,
        fixture_mode: bool = False, auto_approve_fixtures: bool = False,
        approval_timeout_s: float = 60.0,
    ):
        if auto_approve_fixtures and not fixture_mode:
            raise ValueError("automatic approval is allowed only for synthetic fixtures")
        self.agent, self.service, self.feed, self.state, self.budget = agent, service, feed, state, budget
        self.hand_log = Path(hand_log) if hand_log else None
        self.fixture_mode = fixture_mode
        self.auto_approve_fixtures = auto_approve_fixtures
        self.approval_timeout_s = approval_timeout_s
        self.session_id = feed.frame["session_id"]
        self.previous_take_id: str | None = None
        self.seen: set[Path] = set()

    def _await_approval(self, actions: list[dict]) -> bool:
        approval_id = uuid.uuid4().hex
        deadline = time.monotonic() + self.approval_timeout_s
        expires = int(time.time() * 1000 + self.approval_timeout_s * 1000)
        recording_before = self.state.recording_counter()
        summary = "Tap the pedal to start the drill, or approve these rig changes on the dashboard."
        self.feed.publish(
            state="thinking", mood="encouraging", target="player", cue=summary,
            awaiting_approval={"id": approval_id, "summary": summary,
                               "actions": actions, "expires_unix_ms": expires},
        )
        print(f"Approval needed: {actions}. Tap pedal or approve in dashboard.")
        if self.auto_approve_fixtures:
            self.feed.publish(awaiting_approval=None)
            return True
        while time.monotonic() < deadline:
            decision = self.feed.poll_decision(approval_id)
            if decision:
                self.feed.publish(awaiting_approval=None)
                return decision == "approve"
            if self.state.recording_counter() > recording_before:
                self.feed.publish(awaiting_approval=None)
                return True
            time.sleep(0.1)
        self.feed.publish(awaiting_approval=None)
        return False

    def _invoke(self, message: str, take_id: str) -> dict:
        from langchain_core.callbacks import UsageMetadataCallbackHandler
        from langgraph.types import Command

        if not self.budget.allow_new_run():
            self.feed.publish(state="asleep", mood="sleepy", target=None,
                              cue="Coach is out of credit.")
            raise BudgetExhausted("coach budget guard stopped a new model run")
        callback = UsageMetadataCallbackHandler()
        config = {"configurable": {"thread_id": self.session_id},
                  "recursion_limit": 40, "callbacks": [callback]}
        start = time.monotonic()
        try:
            result = self.agent.invoke({"messages": [("user", message)]}, config=config)
            for _ in range(8):
                todos = _todo_frame(result)
                if todos:
                    self.feed.publish(todos=todos)
                actions = _pending_actions(result)
                if not actions:
                    return result
                approved = self._await_approval(actions)
                decisions = ([{"type": "approve"}] * len(actions) if approved else
                             [{"type": "reject", "message": "Player declined or timed out."}] * len(actions))
                if not approved:
                    self.feed.publish(state="speaking", mood="neutral", target="player",
                                      cue="No problem, I'll leave your sound as it is.")
                result = self.agent.invoke(Command(resume={"decisions": decisions}), config=config)
            raise RuntimeError("too many consecutive approval requests")
        finally:
            entry = self.budget.record(take_id, callback.usage_metadata, time.monotonic() - start)
            LOG.info("coach take %s used %s tokens; estimated upper-bound $%.4f in %.2fs",
                     take_id, callback.usage_metadata, entry["estimated_upper_bound_usd"], entry["elapsed_s"])

    def process_take(self, wav: Path, sidecar_path: Path | None = None) -> dict:
        """Analyze one completed take, invoke the agent, and publish its plan."""
        from tools.ears.analyze import analyze_take

        wav = Path(wav)
        sidecar_path = Path(sidecar_path) if sidecar_path else wav.with_suffix(".json")
        sidecar = json.loads(sidecar_path.read_text())
        take_id = _safe_take_id(sidecar["take_id"])
        self.feed.publish(take_id=take_id, state="listening", mood="concentrating",
                          target="loop", cue=None, todos=[], drill_card=None,
                          before_after=None, awaiting_approval=None)
        ear = analyze_take(wav, sidecar_path)
        log_path = self.hand_log
        if self.fixture_mode:
            log_path = wav.with_name(f"{take_id}.hands.jsonl")
        hand = hand_report(log_path, sidecar, fixture_mode=self.fixture_mode)
        folder = self.service.workspace / "takes" / take_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "take.json").write_text(ear.to_json() + "\n")
        (folder / "hand.json").write_text(json.dumps(hand, indent=2) + "\n")
        self.service.current_take_id = take_id
        self.feed.publish(state="thinking", mood="aha" if ear.findings else "curious", target="coach")
        print(f"Take {take_id}: {ear.summary}; hand: {hand.get('summary', 'unavailable')}")
        before = self.previous_take_id
        prompt = f"New take {take_id}. Diagnose from reports, choose one drill, set up the rig."
        if before:
            result = self.service.compare_takes(before, take_id)
            prompt += f" Previous take: {before}. Compare before and after using compare_takes."
            if result["improved"]:
                self.feed.publish(state="pleased", mood="proud", target="player")
        result = self._invoke(prompt, take_id)
        self.previous_take_id = take_id
        return result

    def run_directory(self, take_dir: Path, *, once: bool = False) -> None:
        """Poll completed sidecars; a coach failure never stops the instrument."""
        take_dir = Path(take_dir)
        self.feed.publish(state="idle", mood="neutral", target="player",
                          cue="Play me something. Tap the pedal to record.")
        while True:
            for sidecar in sorted(take_dir.glob("*.json")):
                if sidecar in self.seen:
                    continue
                try:
                    data = json.loads(sidecar.read_text())
                    if not isinstance(data, dict) or not data.get("wav") or not data.get("take_id"):
                        continue
                    wav = sidecar.parent / Path(data["wav"]).name
                    if not wav.is_file():
                        continue
                    self.seen.add(sidecar)
                    self.process_take(wav, sidecar)
                except Exception:
                    if not self.budget.allow_new_run():
                        self.feed.publish(state="asleep", mood="sleepy", target=None,
                                          cue="Coach is out of credit.")
                        return
                    LOG.exception("coach could not process %s", sidecar.name)
                    self.feed.publish(state="asleep", mood="sleepy", target=None,
                                      cue="Coach hit a problem; the rig is fine.")
            if once:
                return
            time.sleep(0.5)
