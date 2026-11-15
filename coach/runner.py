"""Watch completed takes, analyze off-thread from audio, and run the coach."""
from __future__ import annotations

import json
import logging
import math
import threading
import time
import uuid
from pathlib import Path

from .budget import BudgetGuard
from .feed import CoachFeed
from .memory import last_time_cue, remember_comparison
from .rig import RigStateReader, control_message
from .session import PracticeSession
from .tools import CoachTools, _safe_take_id


LOG = logging.getLogger(__name__)


class BudgetExhausted(RuntimeError):
    """No more paid model calls are allowed this session."""


class _OfflineUsageCollector:
    """No-dependency callback placeholder for injected offline fake agents only."""

    def __init__(self):
        self.usage_metadata = {}
        self._lock = threading.Lock()


def _hesitation_mark(report: dict) -> dict | None:
    """Turn the strongest measured audio gap into a take-relative loop mark."""
    findings = report.get("findings") or []
    pauses = [item for item in findings if isinstance(item, dict) and item.get("type") == "hesitation"]
    pauses.sort(key=lambda item: item.get("extra_ms", 0), reverse=True)
    for finding in pauses:
        at, gap = finding.get("at_ms"), finding.get("gap_ms")
        if (not isinstance(at, (int, float)) or isinstance(at, bool) or
                not isinstance(gap, (int, float)) or isinstance(gap, bool) or
                not math.isfinite(at) or not math.isfinite(gap) or gap <= 0 or at < gap):
            continue
        extra = finding.get("extra_ms")
        label = (f"{round(extra):g} ms late" if isinstance(extra, (int, float)) and not isinstance(extra, bool)
                 and extra > 0 else f"{gap:g} ms gap")
        return {"start_s": round((at - gap) / 1000, 3),
                "end_s": round(at / 1000, 3),
                "label": label[:24]}   # same number Riff quotes and the practice card shows
    return None


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
        if control in {"bypass", "loop"} and any(item["control"] == control for item in actions):
            raise ValueError("duplicate toggle action in one approval batch")
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


def technique_report(log_path: Path | None, sidecar: dict, ear: dict, *, fixture_mode: bool) -> dict | None:
    """What each hand did at every chord change (vision/technique.py); None without a camera log."""
    if fixture_mode or log_path is None or not log_path.is_file():
        return None
    try:
        from vision.technique import report_for_take
        return report_for_take(log_path, sidecar, ear)
    except Exception as exc:   # never lose the take over the camera analysis
        LOG.warning("technique report unavailable: %s", exc)
        return {"available": False, "reason": "analysis failed"}


# The diagnose step's choice of drill: the measured cause decides it, not habit.
SKILL_MAP = (
    "Pick the drill skill from the top technique finding in get_hand_report: late_finger or pattern "
    "-> lead-with-the-last-finger, late_start -> move-on-the-and, slow_change or finger_wander -> "
    "shortest-path, picking_stop -> keep-the-hand-moving; no camera cause -> isolate-the-change. "
    "Call a change by its time; name chords only if the player said which change it is. "
    "Write pass_rule as 'worst gap under N ms' (the session judges that number); put the finger or "
    "timing cue in the passage. "
)


class CoachRunner:
    """Owns take processing; injected agent/feed/state permit no-network tests."""

    def __init__(
        self, agent, service: CoachTools, feed: CoachFeed, state: RigStateReader,
        budget: BudgetGuard, *, hand_log: Path | None = None,
        fixture_mode: bool = False, auto_approve_fixtures: bool = False,
        approval_timeout_s: float = 60.0, quiet_until_asked: bool = False,
    ):
        if auto_approve_fixtures and not fixture_mode:
            raise ValueError("automatic approval is allowed only for synthetic fixtures")
        self.agent, self.service, self.feed, self.state, self.budget = agent, service, feed, state, budget
        self.hand_log = Path(hand_log) if hand_log else None
        self.fixture_mode = fixture_mode
        self.auto_approve_fixtures = auto_approve_fixtures
        self.approval_timeout_s = approval_timeout_s
        # Live rig: stay in quiet free play (no model calls) until the player starts practice with Y / the
        # pedal hold, or says or types a goal. Loops made while jamming are not coached.
        self.quiet_until_asked = quiet_until_asked
        self.session_id = feed.frame["session_id"]
        self.previous_take_id: str | None = None
        self.seen: set[Path] = set()
        self.player_note: str | None = None
        self._session_active = False
        self._last_practice_count = 0
        self._last_recording_count = state.recording_counter()

    def _speak(self, text: str) -> None:
        """Voice a runner-written cue (live rig only) without ever blocking the take loop."""
        if not self.quiet_until_asked or not text:
            return

        def work() -> None:
            try:
                import asyncio
                from .voice import Voice
                audio = asyncio.run(Voice.from_env().render(text))
                if audio is not None:
                    self.feed.broadcast_audio(audio)
            except Exception as exc:  # voice is optional
                LOG.warning("coach voice for a short cue failed: %s: %s", type(exc).__name__, exc)

        threading.Thread(target=work, name="omniriff-cue-voice", daemon=True).start()

    def _poll_player_input(self) -> None:
        """Consume bounded player words outside recording and keep them as data."""
        snapshot = self.state.snapshot()
        if (snapshot.get("loop") or {}).get("state") == "recording":
            return
        text = self.feed.poll_said()
        if text is None:
            return
        text = " ".join(text.split())[:240]
        if not text:
            return
        if self.service.session.mode == "play":
            self.service.session = PracticeSession(last_time=last_time_cue(self.service.workspace))
            self.previous_take_id = None
            self._session_active = True
            self.feed.publish(before_after=None, drill_card=None, mark=None, todos=[])
        journal = self.service.workspace / "journal" / _safe_take_id(self.session_id)
        journal.mkdir(parents=True, exist_ok=True)
        if self.previous_take_id is None and self.service.session.mode == "practice":
            goal = text[:80].rsplit(" ", 1)[0] if len(text) > 80 and " " in text[:80] else text[:80]
            self.service.session.plan(
                goal=goal, next_step="Isolate the measured trouble spot",
                drill_count=2, attempt_count=3,
                drill_titles=["Fix the measured cause", "Full pattern over your loop"],
            )
            (journal / "goal.md").write_text(f"# Player's practice goal\n\n{goal}\n")
            self.feed.publish(session=self.service.session.snapshot(), state="speaking",
                              mood="encouraging", target="player",
                              cue="Got it, we'll work on that. Tap the pedal, play it for me, then tap again.")
            self._speak("Got it, we'll work on that. Tap the pedal, play it for me, then tap again.")
            self.feed.publish_activity("coach", "write /journal/goal.md", "done")
        else:
            self.player_note = text
            with (journal / "notes.md").open("a") as stream:
                stream.write(text + "\n")
            cue = "Got it, I'll keep that in mind for the next take."
            self.feed.publish(state="speaking", mood="encouraging", target="player",
                              cue=cue)
            self._speak(cue)
            self.feed.publish_activity("coach", "write /journal/notes.md", "done")

    def _poll_practice_action(self) -> None:
        """A new accepted R24 pedal count starts or pauses practice."""
        pedal = self.state.snapshot().get("pedal") or {}
        count = pedal.get("practice_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            return
        if count < self._last_practice_count:
            # The engine restarted; its counter starts again at zero.
            self._last_practice_count = count
            return
        if count == self._last_practice_count:
            return
        self._last_practice_count = count
        if self._session_active and self.service.session.mode == "practice":
            self.service.session.stop()
            self._session_active = False
            self.feed.publish(session=self.service.session.snapshot(), state="idle",
                              mood="neutral", target="player", cue="Practice paused. Free play is yours.",
                              mark=None, drill_card=None)
            return
        if self.service.session.mode != "practice" or self.previous_take_id is not None:
            self.service.session = PracticeSession(last_time=last_time_cue(self.service.workspace))
        self.previous_take_id = None
        self.player_note = None
        self._session_active = True
        self.feed.publish(session=self.service.session.snapshot(), state="idle", mood="neutral",
                          target="player", cue="What are you working on? Hold TALK or type it, then play.",
                          mark=None, drill_card=None, before_after=None, todos=[])

    def _await_approval(self, actions: list[dict]) -> bool:
        approval_id = uuid.uuid4().hex
        deadline = time.monotonic() + self.approval_timeout_s
        expires = int(time.time() * 1000 + self.approval_timeout_s * 1000)
        pedal_before = (self.state.snapshot().get("pedal") or {}).get("practice_count")
        if not isinstance(pedal_before, int) or isinstance(pedal_before, bool) or pedal_before < 0:
            pedal_before = None
        summary = "Hold the pedal to approve the rig change, or approve it on the dashboard."
        self.feed.publish(
            state="thinking", mood="encouraging", target="player", cue=summary,
            awaiting_approval={"id": approval_id, "summary": summary,
                               "actions": actions, "expires_unix_ms": expires},
        )
        self.feed.publish_activity("coach", "rig_control approval", "waiting")
        print(f"Approval needed: {actions}. Hold pedal or approve in dashboard.")
        if self.auto_approve_fixtures:
            self.feed.publish(awaiting_approval=None)
            self.feed.publish_activity("coach", "rig_control approval", "done")
            return True
        while time.monotonic() < deadline:
            decision = self.feed.poll_decision(approval_id)
            if decision:
                self.feed.publish(awaiting_approval=None)
                self.feed.publish_activity("coach", "rig_control approval", "done" if decision == "approve" else "failed")
                return decision == "approve"
            count = (self.state.snapshot().get("pedal") or {}).get("practice_count")
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                if pedal_before is None or count < pedal_before:
                    pedal_before = count  # reconnect/counter reset is not approval
                elif count > pedal_before:
                    self._last_practice_count = count  # do not pause practice on the next poll
                    self.feed.publish(awaiting_approval=None)
                    self.feed.publish_activity("coach", "rig_control approval", "done")
                    return True
            time.sleep(0.1)
        self.feed.publish(awaiting_approval=None)
        self.feed.publish_activity("coach", "rig_control approval", "failed")
        return False

    def _invoke(self, message: str, take_id: str) -> dict:
        if not self.budget.allow_new_run():
            self.feed.publish(state="asleep", mood="sleepy", target=None,
                              cue="Coach is out of credit.")
            raise BudgetExhausted("coach budget guard stopped a new model run")
        gate = getattr(self.service, "model_gate", None)
        try:
            from langchain_core.callbacks import UsageMetadataCallbackHandler
        except ImportError:
            if gate is not None:
                raise RuntimeError("live coach requires langchain_core for usage accounting") from None
            callback = _OfflineUsageCollector()
        else:
            callback = UsageMetadataCallbackHandler()
        if gate is not None:
            gate.bind(callback)
        callbacks = [callback]
        try:
            from langchain_core.callbacks import BaseCallbackHandler

            runner = self
            live = self.quiet_until_asked

            class _ToolLog(BaseCallbackHandler):
                """One terminal line per tool call, and (live rig) the real plan and harness steps on the
                dashboard as they happen: the todo list, subagent runs, skill reads, memory writes."""
                def __init__(self):
                    self._subagents: dict = {}

                def _show(self, who, what, status):
                    try:
                        runner.feed.publish_activity(who, what[:60], status)
                    except Exception:  # the dashboard strip must never break the coach
                        LOG.debug("activity not shown", exc_info=True)

                def on_tool_start(self, serialized, input_str, **kw):
                    name = (serialized or {}).get("name") or kw.get("name")
                    LOG.info("coach tool -> %s %s", name, str(input_str)[:160])
                    if not live:
                        return
                    args = kw.get("inputs") if isinstance(kw.get("inputs"), dict) else {}
                    try:
                        if name == "write_todos":
                            todos = _todo_frame(args)
                            if todos:
                                runner.feed.publish(todos=todos)
                        elif name == "task":
                            sub = str(args.get("subagent_type") or "subagent")
                            self._subagents[kw.get("run_id")] = sub
                            self._show("coach", f"subagent {sub}", "running")
                        elif name == "read_file" and str(args.get("file_path", "")).startswith("/skills/"):
                            skill = str(args["file_path"]).split("/")[2]
                            self._show("coach", f"open skill {skill}", "done")
                        elif name == "edit_file" and str(args.get("file_path", "")).startswith("/memories/"):
                            self._show("coach", "write /memories/player.md", "done")
                    except Exception:
                        LOG.debug("plan/activity frame skipped", exc_info=True)

                def on_tool_end(self, output, **kw):
                    LOG.info("coach tool <- %s", str(getattr(output, "content", output))[:160])
                    sub = self._subagents.pop(kw.get("run_id"), None)
                    if live and sub:
                        self._show("coach", f"subagent {sub}", "done")

            callbacks.append(_ToolLog())
        except ImportError:
            pass
        config = {"configurable": {"thread_id": self.session_id},
                  "recursion_limit": 60, "callbacks": callbacks}
        start = time.monotonic()
        try:
            result = self.agent.invoke({"messages": [("user", message)]}, config=config)
            if gate is not None and gate.refused:
                raise BudgetExhausted("coach budget guard refused a specialist model call")
            for _ in range(8):
                todos = _todo_frame(result)
                if todos:
                    self.feed.publish(todos=todos)
                    self.feed.publish_activity("coach", "write_todos", "done")
                actions = _pending_actions(result)
                if not actions:
                    try:
                        last = result["messages"][-1]
                        LOG.info("coach final message: %s", str(getattr(last, "content", last))[:400])
                    except Exception:
                        pass
                    return result
                approved = self._await_approval(actions)
                decisions = ([{"type": "approve"}] * len(actions) if approved else
                             [{"type": "reject", "message": "Player declined or timed out."}] * len(actions))
                if not approved:
                    self.feed.publish(state="speaking", mood="neutral", target="player",
                                      cue="No problem, I'll leave your sound as it is.")
                from langgraph.types import Command
                result = self.agent.invoke(Command(resume={"decisions": decisions}), config=config)
                if gate is not None and gate.refused:
                    raise BudgetExhausted("coach budget guard refused a resumed model call")
            raise RuntimeError("too many consecutive approval requests")
        except BudgetExhausted as exc:
            LOG.warning("coach budget guard stopped this run (%s): estimated spend $%.2f of $%.2f cap in %s",
                        exc, self.budget.spent_usd(), self.budget.limit_usd, self.budget.path)
            self.feed.publish(state="asleep", mood="sleepy", target=None,
                              cue="Coach is out of credit; keep playing without me.")
            raise
        finally:
            if gate is not None:
                gate.bind(None)
            if callback.usage_metadata or gate is None:
                try:
                    entry = self.budget.record(take_id, callback.usage_metadata, time.monotonic() - start)
                except (OSError, ValueError, TypeError, RuntimeError) as exc:
                    self.feed.publish(state="asleep", mood="sleepy", target=None,
                                      cue="Coach cannot account for model usage; keep playing without me.")
                    raise BudgetExhausted("coach usage ledger is unavailable") from exc
                LOG.info("coach take %s used %s tokens; estimated upper-bound $%.4f in %.2fs",
                         take_id, callback.usage_metadata, entry["estimated_upper_bound_usd"], entry["elapsed_s"])
            elif gate.admitted_count:
                self.feed.publish(state="asleep", mood="sleepy", target=None,
                                  cue="Coach cannot verify model usage; keep playing without me.")
                raise BudgetExhausted("model usage metadata is unavailable")

    def process_take(self, wav: Path, sidecar_path: Path | None = None) -> dict:
        """Analyze one completed take, invoke the agent, and publish its plan."""
        from tools.ears.analyze import analyze_take

        self._poll_player_input()
        wav = Path(wav)
        sidecar_path = Path(sidecar_path) if sidecar_path else wav.with_suffix(".json")
        sidecar = json.loads(sidecar_path.read_text())
        take_id = _safe_take_id(sidecar["take_id"])
        if self.service.session.mode == "play":
            return {"skipped": "free_play", "take_id": take_id}
        self._session_active = True
        # Live rig: answer at once (text + cached voice) so the ~20 s of model work isn't dead silence.
        ack = "Okay, let me listen back to that." if self.quiet_until_asked else None
        self.feed.publish(take_id=take_id, state="listening", mood="concentrating",
                          target="loop", cue=ack, todos=[],
                          before_after=None, awaiting_approval=None, activity=[], mark=None)
        if ack:
            self._speak(ack)
        self.feed.publish_activity("ears", "analyze_take", "running")
        ear = analyze_take(wav, sidecar_path)
        self.feed.publish_activity("ears", "analyze_take", "done")
        log_path = self.hand_log
        if self.fixture_mode:
            log_path = wav.with_name(f"{take_id}.hands.jsonl")
        hand = hand_report(log_path, sidecar, fixture_mode=self.fixture_mode)
        technique = technique_report(log_path, sidecar, json.loads(ear.to_json()), fixture_mode=self.fixture_mode)
        if technique is not None:
            hand = {**hand, "technique": technique}
            self.feed.publish_activity("eyes", "technique: fingers + picking hand",
                                       "done" if technique.get("available") else "failed")
        self.feed.publish_activity("eyes", "report_for_window", "done" if hand.get("available", True) else "failed")
        folder = self.service.workspace / "takes" / take_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "take.json").write_text(ear.to_json() + "\n")
        (folder / "hand.json").write_text(json.dumps(hand, indent=2) + "\n")
        self.service.current_take_id = take_id
        report = json.loads(ear.to_json())
        if ear.judgeable:
            self.service.session.record_take(report)
        mark = _hesitation_mark(report) if ear.judgeable else None
        if self.quiet_until_asked:
            # Live rig: show the gap marker together with Riff's explanation (when it speaks), not before it
            # has said anything, so the marker never appears unexplained.
            self.service.pending_mark = mark
            self.feed.publish(state="thinking", mood="aha" if ear.findings else "curious",
                              target="coach", session=self.service.session.snapshot())
        else:
            self.feed.publish(state="thinking", mood="aha" if ear.findings else "curious",
                              target="loop" if mark else "coach", mark=mark,
                              session=self.service.session.snapshot())
        print(f"Take {take_id}: {ear.summary}; hand: {hand.get('summary', 'unavailable')}")
        if not ear.judgeable:
            self.feed.publish(state="idle", mood="neutral", target="player",
                              cue=f"{ear.summary} Play at least {ear.min_strums} strums and try again.")
            self.feed.publish_activity("coach", "judge take", "failed")
            return {"skipped": "unjudgeable", "take_id": take_id}
        before = self.previous_take_id
        action = self.service.session.next_action(take_id)
        comparison = None
        if before:
            comparison = self.service.compare_takes(before, take_id)
        if action["action"] == "advance":
            self.service.session.advance_drill(
                passed=action["passed"], next_step="Full pattern over your loop")
            self.feed.publish(session=self.service.session.snapshot(), drill_card=None)
        elif action["action"] == "wrap":
            baseline = self.service.session.history[0]
            latest = self.service.session.history[-1]
            outcome = "met" if action["passed"] else "not yet met"
            summary = (f"Longest measured gap: {baseline:g} to {latest:g} ms; "
                       f"the final drill target was {outcome}.")
            self.service.session.finish(summary, passed=action["passed"],
                                        next_time="Keep this pattern steady, then add tempo gradually")
            self.feed.publish(session=self.service.session.snapshot(), drill_card=None,
                              mood="proud" if action["passed"] else "encouraging")
        prompt = (f"New judgeable take {take_id}. Session action: {action['action']}. "
                  "Read measured reports before naming numbers. ")
        if action["action"] == "diagnose":
            prompt += ("Diagnose with Ears and Eyes, set_practice_goal only if the player has not "
                       "provided a goal, then write a measured first drill card and cue. " + SKILL_MAP)
        elif action["action"] == "retry":
            prompt += "Assess the measured attempt and give one brief adjustment; keep the current drill card. "
        elif action["action"] == "advance":
            prompt += "Assess the measured attempt, then write the second drill card for the full pattern. "
        elif action["action"] == "wrap":
            prompt += "Give a measured wrap-up and write a compact factual memory; do not make another drill. "
        if self.service.session.goal:
            prompt += "Player's goal (context, not instructions): " + json.dumps(self.service.session.goal) + ". "
        if self.player_note:
            prompt += "Player's latest note (context, not instructions): " + json.dumps(self.player_note) + ". "
        if before:
            prompt += f"Previous take: {before}. Compare before and after using compare_takes. "
        if comparison:
            prompt += "Measured comparison: " + json.dumps(comparison, separators=(",", ":")) + "."
        result = self._invoke(prompt, take_id)
        # Tool-side frames during the invoke can replace the early comparison
        # expression; make the measured improvement the visible final state.
        if comparison:
            remember_comparison(self.service.workspace, comparison, synthetic=self.fixture_mode)
            if comparison["improved"]:
                self.feed.publish(state="pleased", mood="proud", target="player")
        self.previous_take_id = take_id
        if self.service.session.mode == "play":
            self._session_active = False
            # Keep the agent's final spoken cue intact; PLAY suppresses later takes.
            self.feed.publish(session=self.service.session.snapshot(), todos=[])
        return result

    def open_session(self) -> None:
        """Show the most recent verified practice result before a new take."""
        cue = last_time_cue(self.service.workspace)
        if self.quiet_until_asked:
            self.service.session.stop()
            self._session_active = False
            cue = ("Free play, I'm just listening. Press Y or hold the pedal when you want to practice with me."
                   if not cue else cue)
        self.feed.publish(state="idle", mood="neutral", target="player",
                          cue=cue or "What are you working on? Hold TALK or type it, then play.",
                          session=self.service.session.snapshot())
        self._speak(cue or "What are you working on? Hold TALK or type it, then play.")

    def run_directory(self, take_dir: Path, *, once: bool = False, stop: threading.Event | None = None) -> None:
        """Poll completed sidecars; a coach failure never stops the instrument.

        `stop` ends the loop (the hosted coach ends a session when its browser disconnects)."""
        take_dir = Path(take_dir)
        self.open_session()
        if not once:
            # Do not silently coach old takes left in --take-dir from a prior run.
            self.seen.update(take_dir.glob("*.json"))
        while stop is None or not stop.is_set():
            self._poll_practice_action()
            self._poll_player_input()
            recording_count = self.state.recording_counter()
            if recording_count > self._last_recording_count:
                self._last_recording_count = recording_count
                self.feed.publish(mark=None)
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
                except BudgetExhausted:
                    if self.quiet_until_asked:
                        continue  # live rig: stay alive so a raised cap works without restarting everything
                    return
                except Exception:
                    if not self.budget.allow_new_run():
                        self.feed.publish(state="asleep", mood="sleepy", target=None,
                                          cue="Coach is out of credit.")
                        if self.quiet_until_asked:
                            continue
                        return
                    LOG.exception("coach could not process %s", sidecar.name)
                    # Plain-words reason; the full traceback is in the terminal log above.
                    self.feed.publish(state="idle", mood="neutral", target="player",
                                      cue="I couldn't finish that take. Your rig is fine, play another take.")
            if once:
                return
            time.sleep(0.5)
