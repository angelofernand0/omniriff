"""Evidence-backed tools exposed to the coach and its Ears/Eyes subagents."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .feed import CoachFeed
from .rig import RigClient, RigStateReader


TAKE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SKILLS = frozenset({"isolate-the-change", "slow-then-speed-up", "dry-check", "keep-the-hand-moving"})


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
        self.current_take_id: str | None = None

    def _report(self, take_id: str, name: str) -> dict:
        take_id = _safe_take_id(take_id)
        path = self.workspace / "takes" / take_id / name
        if not path.is_file():
            return {"available": False, "take_id": take_id}
        return json.loads(path.read_text())

    def get_rig_state(self) -> dict:
        """Read the latest engine state; never infer a rig state when disconnected."""
        return self.state.snapshot()

    def get_take_report(self, take_id: str) -> dict:
        """Read measured strum times and hesitations for a recorded take."""
        report = self._report(take_id, "take.json")
        self.feed.publish(state="thinking", mood="concentrating", target="loop")
        return report

    def get_hand_report(self, take_id: str) -> dict:
        """Read measured strumming-hand stalls; unavailable means no hand claim."""
        report = self._report(take_id, "hand.json")
        self.feed.publish(state="thinking", mood="concentrating", target="hand")
        return report

    def compare_takes(self, before_id: str, after_id: str) -> dict:
        """Compare two measured takes, returning counts, worst gaps, and stability."""
        before = self._report(before_id, "take.json")
        after = self._report(after_id, "take.json")
        if not before.get("available", True) or not after.get("available", True):
            raise ValueError("both TakeReports are required for comparison")
        bh, bg, bs = _numbers(before)
        ah, ag, ass = _numbers(after)
        result = {
            "before_take_id": _safe_take_id(before_id),
            "after_take_id": _safe_take_id(after_id),
            "hesitations": [bh, ah], "worst_gap_ms": [bg, ag],
            "tempo_stability": [bs, ass],
            "improved": ag < bg and ah <= bh,
        }
        self.feed.publish(before_after=result, mood="proud" if result["improved"] else "concentrating")
        return result

    def write_drill_card(self, skill: str, passage: str, reps: int, pass_rule: str, rig: dict) -> str:
        """Save one specific practice drill; rig settings here are proposals only."""
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
        self.feed.publish(drill_card=card, mood="encouraging", target="player")
        path.write_text(json.dumps(card, indent=2) + "\n")
        return journal_path

    def say(self, text: str) -> str:
        """Speak one short cause-and-fix cue grounded in the reports."""
        if not isinstance(text, str) or not 1 <= len(text) <= 240:
            raise ValueError("cue must be 1–240 characters")
        # A simple punctuation guard; models can use decimal numbers in reports.
        if len(re.findall(r"[.!?](?:\s|$)", text)) > 2:
            raise ValueError("cue must be at most two sentences")
        self.feed.publish(state="speaking", mood="concerned", target="player", cue=text)
        return text

    def rig_control(self, control: str, value: float | None = None) -> str:
        """After the human approves this tool call, send one schema-valid rig event."""
        message = self.rig.send(control, value)
        self.feed.publish(state="pointing", mood="encouraging", target=control)
        return f"{'Fixture logged' if self.rig.fixture_mode else 'Sent'} {message['type']} {control}"


def build_langchain_tools(service: CoachTools) -> dict:
    """Wrap the plain methods as named LangChain tools without importing them in CI."""
    from langchain_core.tools import tool

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
    def write_drill_card(skill: str, passage: str, reps: int, pass_rule: str, rig: dict) -> str:
        """Save a measurable drill card; proposed rig settings still need approval."""
        return service.write_drill_card(skill, passage, reps, pass_rule, rig)

    @tool
    def say(text: str) -> str:
        """Say at most two sentences: the measured cause, then one fix."""
        return service.say(text)

    @tool
    def rig_control(control: str, value: float | None = None) -> str:
        """Request one rig change. This tool is interrupted for human approval."""
        return service.rig_control(control, value)

    return {item.name: item for item in (
        get_rig_state, get_take_report, get_hand_report, compare_takes,
        write_drill_card, say, rig_control,
    )}
