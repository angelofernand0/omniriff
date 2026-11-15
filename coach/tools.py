"""Evidence-backed tools exposed to the coach and its Ears/Eyes subagents."""
from __future__ import annotations

import logging

import asyncio
import json
import re
from pathlib import Path

from .feed import CoachFeed
from .memory import last_time_cue
from .rig import RigClient, RigStateReader
from .session import PracticeSession


TAKE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SKILLS = frozenset({"isolate-the-change", "slow-then-speed-up", "dry-check", "keep-the-hand-moving"})


LOG = logging.getLogger(__name__)


def _safe_take_id(take_id: str) -> str:
    if not isinstance(take_id, str) or not TAKE_ID.fullmatch(take_id) or take_id in {".", ".."}:
        raise ValueError("invalid take id")
    return take_id


def _numbers(report: dict) -> tuple[int, float, float]:
    hes = [item for item in report.get("findings", []) if item.get("type") == "hesitation"]
    intervals = report.get("intervals_ms", [])
    worst = max((float(x) for x in intervals), default=0.0)
    return len(hes), worst, float(report.get("tempo_stability") or 0.0)


class CoachTools:
    """Plain tool functions with one confined workspace and one feed."""

    def __init__(self, workspace: Path, feed: CoachFeed, rig: RigClient, state: RigStateReader):
        self.workspace = Path(workspace)
        self.feed = feed
        self.rig = rig
        self.state = state
        last_time = last_time_cue(self.workspace)
        self.session = PracticeSession(last_time=last_time if last_time and len(last_time) <= 120 else None)
        self.current_take_id: str | None = None
        self._read_take_ids: set[str] = set()

    def _report(self, take_id: str, name: str) -> dict:
        take_id = _safe_take_id(take_id)
        path = self.workspace / "takes" / take_id / name
        if not path.is_file():
            return {"available": False, "take_id": take_id}
        return json.loads(path.read_text())

    def get_rig_state(self) -> dict:
        """Read the latest engine state; never infer a rig state when disconnected."""
        snapshot = self.state.snapshot()
        self.feed.publish_activity("coach", "get_rig_state", "failed" if snapshot.get("available") is False else "done")
        return snapshot

    def get_take_report(self, take_id: str) -> dict:
        """Read measured strum times and hesitations for a recorded take."""
        report = self._report(take_id, "take.json")
        self.session.record_take(report)
        if self.session.has_take(take_id):
            self._read_take_ids.add(take_id)
        self.feed.publish(state="thinking", mood="concentrating", target="loop",
                          session=self.session.snapshot())
        self.feed.publish_activity("ears", "get_take_report", "done" if report.get("available", True) else "failed")
        return report

    def get_hand_report(self, take_id: str) -> dict:
        """Read measured strumming-hand stalls; unavailable means no hand claim."""
        report = self._report(take_id, "hand.json")
        self.feed.publish(state="thinking", mood="concentrating", target="hand")
        self.feed.publish_activity("eyes", "get_hand_report", "done" if report.get("available", True) else "failed")
        return report

    def set_practice_goal(self, goal: str) -> str:
        """Publish a measured goal only when the player has not supplied one."""
        if self.current_take_id is None or self.current_take_id not in self._read_take_ids:
            raise ValueError("read a judgeable first TakeReport before setting a goal")
        if self.session.mode != "practice" or self.session.goal is not None:
            raise ValueError("practice goal already set or session ended")
        self.session.plan(
            goal=goal, next_step="Isolate the measured trouble spot",
            drill_count=2, attempt_count=3,
            drill_titles=["Isolate the trouble spot", "Full pattern over your loop"],
        )
        self.feed.publish(session=self.session.snapshot())
        self.feed.publish_activity("coach", "set_practice_goal", "done")
        return goal

    def compare_takes(self, before_id: str, after_id: str) -> dict:
        """Compare two measured takes, returning counts, worst gaps, and stability."""
        before = self._report(before_id, "take.json")
        after = self._report(after_id, "take.json")
        if not before.get("available", True) or not after.get("available", True):
            raise ValueError("both TakeReports are required for comparison")
        if before.get("judgeable") is not True or after.get("judgeable") is not True:
            raise ValueError("both TakeReports must have enough strums to judge timing")
        self.session.record_take(before)
        self.session.record_take(after)
        bh, bg, bs = _numbers(before)
        ah, ag, ass = _numbers(after)
        result = {
            "before_take_id": _safe_take_id(before_id),
            "after_take_id": _safe_take_id(after_id),
            "hesitations": [bh, ah], "worst_gap_ms": [bg, ag],
            "tempo_stability": [bs, ass],
            "improved": ag < bg and ah <= bh,
        }
        self.feed.publish(before_after=result, mood="proud" if result["improved"] else "concentrating",
                          session=self.session.snapshot())
        self.feed.publish_activity("coach", "compare_takes", "done")
        return result

    def write_drill_card(self, skill: str, passage: str, reps: int, pass_rule: str, rig: dict) -> str:
        """Save one specific practice drill; rig settings here are proposals only."""
        if self.session.mode != "practice":
            raise ValueError("practice session is not active")
        if skill not in SKILLS:
            raise ValueError("unknown drill skill")
        if not isinstance(passage, str) or not 1 <= len(passage) <= 80:
            raise ValueError("passage must be 1–80 characters")
        if not isinstance(reps, int) or isinstance(reps, bool) or not 1 <= reps <= 20:
            raise ValueError("reps must be 1–20")
        if not isinstance(pass_rule, str) or not 1 <= len(pass_rule) <= 120:
            raise ValueError("pass_rule must be 1–120 characters")
        if not isinstance(rig, dict) or set(rig) - {"bypass", "filter", "reverb"}:
            raise ValueError("invalid rig proposal")
        if "bypass" in rig and not isinstance(rig["bypass"], bool):
            raise ValueError("bypass proposal must be boolean")
        for control in ("filter", "reverb"):
            if control in rig and (not isinstance(rig[control], (int, float)) or isinstance(rig[control], bool)
                                   or not 0 <= rig[control] <= 1):
                raise ValueError(f"{control} proposal must be 0–1")
        take_id = _safe_take_id(self.current_take_id or "session")
        session_id = _safe_take_id(self.feed.frame["session_id"])
        folder = self.workspace / "journal" / session_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{take_id}.json"
        journal_path = f"/journal/{session_id}/{take_id}.json"
        card = {
            "skill": skill, "title": skill.replace("-", " ").title(),
            "passage": passage, "reps": reps, "pass_rule": pass_rule,
            "rig": rig, "journal_path": journal_path,
        }
        # Validate the full snapshot before persisting, so the dashboard can render it.
        self.session.set_drill_card(card)
        self.feed.publish(drill_card=card, mood="encouraging", target="player",
                          session=self.session.snapshot())
        path.write_text(json.dumps(card, indent=2) + "\n")
        self.feed.publish_activity("coach", "write_drill_card", "done")
        return journal_path

    def say(self, text: str) -> str:
        """Speak one short cause-and-fix cue grounded in the reports."""
        if not isinstance(text, str) or not 1 <= len(text) <= 240:
            raise ValueError("cue must be 1–240 characters")
        # A simple punctuation guard; models can use decimal numbers in reports.
        if len(re.findall(r"[.!?](?:\s|$)", text)) > 2:
            raise ValueError("cue must be at most two sentences")
        extra = {}
        pending = getattr(self, "pending_mark", None)
        if pending:  # live rig: the gap marker appears with the explanation
            extra = {"mark": pending}
            self.pending_mark = None
        self.feed.publish(state="speaking", mood="concerned", target="loop" if extra else "player", cue=text, **extra)
        self.feed.publish_activity("coach", "say", "done")
        try:
            from .voice import Voice  # supplied by R4; browser speech is the fallback until then
        except ImportError:
            return text
        try:
            voice = Voice.from_env()
            audio = asyncio.run(voice.render(text))
            if audio is None:
                LOG.warning("coach voice: no audio rendered (%s); the dashboard falls back to the browser voice",
                            getattr(voice, "last_error", None) or "no key or empty response")
            else:
                sent = self.feed.broadcast_audio(audio)
                LOG.info("coach voice: %d bytes of MP3 %s", len(audio.get("audio_b64", "")) * 3 // 4,
                         "sent to the dashboard" if sent else "REJECTED by the feed schema")
        except Exception as exc:  # voice is optional: the dashboard retains its browser fallback
            LOG.warning("coach voice failed: %s: %s", type(exc).__name__, exc)
        return text

    def rig_control(self, control: str, value: float | None = None) -> str:
        """After approval, set a parameter or safely start dry bypass/recording."""
        from .rig import control_message

        control_message(control, value, 0, 0)
        if control in {"bypass", "loop"}:
            snapshot = self.state.snapshot()
            if snapshot.get("available") is False:
                self.feed.publish_activity("coach", f"rig_control {control}", "failed")
                return "Rig state unavailable; no toggle sent."
            if control == "bypass":
                current = snapshot.get("bypass")
                desired = True
            else:
                loop = snapshot.get("loop")
                current = loop.get("state") if isinstance(loop, dict) else None
                desired = "recording"
            if current is None or not isinstance(current, bool if control == "bypass" else str):
                self.feed.publish_activity("coach", f"rig_control {control}", "failed")
                return "Rig state incomplete; no toggle sent."
            if current == desired:
                self.feed.publish_activity("coach", f"rig_control {control}", "done")
                return f"{control} already active; no toggle sent."
            if control == "loop" and current != "idle":
                self.feed.publish_activity("coach", f"rig_control {control}", "failed")
                return "Loop is not idle; no toggle sent."
            if self.state.action_pending(control):
                self.feed.publish_activity("coach", f"rig_control {control}", "waiting")
                return f"Awaiting {control} state confirmation; no duplicate toggle sent."
        message = self.rig.send(control, value)
        if control in {"bypass", "loop"}:
            self.state.mark_action_pending(control, desired)
        self.feed.publish(state="pointing", mood="encouraging", target=control)
        self.feed.publish_activity("coach", f"rig_control {control}", "done")
        return f"{'Fixture logged' if self.rig.fixture_mode else 'Sent'} {message['type']} {control}"


def build_langchain_tools(service: CoachTools) -> dict:
    """Wrap the plain methods as named LangChain tools without importing them in CI."""
    from langchain_core.tools import tool as _lc_tool
    import functools

    def tool(fn):
        """Return a rejected call to the model as text so it can fix and retry.

        A ValueError from validation (goal too long, bad rig value...) used to
        propagate and abort the whole coach run for that take.
        """
        @functools.wraps(fn)
        def guarded(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except ValueError as exc:
                return f"Rejected: {exc}. Fix the arguments and call the tool again."
        return _lc_tool(guarded)

    @tool
    def get_rig_state() -> dict:
        """Read the latest live rig state, or unavailable if disconnected."""
        return service.get_rig_state()

    @tool
    def get_take_report(take_id: str) -> dict:
        """Read the measured timing report for a take id; never invent findings."""
        return service.get_take_report(take_id)

    @tool
    def get_hand_report(take_id: str) -> dict:
        """Read the measured strumming-hand report; unavailable means no hand claim."""
        return service.get_hand_report(take_id)

    @tool
    def compare_takes(before_id: str, after_id: str) -> dict:
        """Compare actual before/after timing numbers and publish the result."""
        return service.compare_takes(before_id, after_id)

    @tool
    def set_practice_goal(goal: str) -> str:
        """Set one short goal (at most 80 characters) grounded in the measured first take; do not guess a chord name."""
        return service.set_practice_goal(goal)

    @tool
    def write_drill_card(skill: str, passage: str, reps: int, pass_rule: str, rig: dict) -> str:
        """Save a measurable drill card; proposed rig settings still need approval.

        Limits (a call that breaks one is rejected): passage at most 80 characters; reps 1 to 20;
        pass_rule at most 120 characters; rig is {} or only the keys bypass (true/false), filter (0 to 1)
        and reverb (0 to 1) -- nothing else, no loop or tempo keys."""
        return service.write_drill_card(skill, passage, reps, pass_rule, rig)

    @tool
    def say(text: str) -> str:
        """Say at most two short sentences, about 25 words and never over 180 characters: the measured
        cause, then one fix. It is spoken aloud, so long cues make the player wait."""
        if isinstance(text, str) and len(text) > 180:
            return "Rejected: that is too long to speak. Say it again in under 25 words (180 characters)."
        return service.say(text)

    @tool
    def rig_control(control: str, value: float | None = None) -> str:
        """Request an approved change: filter/reverb value, dry bypass on, or loop start from idle."""
        return service.rig_control(control, value)

    return {item.name: item for item in (
        get_rig_state, get_take_report, get_hand_report, compare_takes, set_practice_goal,
        write_drill_card, say, rig_control,
    )}
